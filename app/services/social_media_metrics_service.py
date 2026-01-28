from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, case
from sqlalchemy.sql import literal_column

from app.db.session import AsyncSessionLocal
from app.models.social_media_record import SocialMediaRecord
from sqlalchemy import cast, Date, text


async def get_social_media_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return aggregated metrics for social_media_records.

    Metrics returned:
    - total_records
    - total_comments
    - total_tweets
    - total_posts
    - unique_users
    - unique_networks
    - min_date
    - max_date
    - total_interaccion
    - total_audiencia_interaccion
    - avg_interaccion
    - avg_audiencia_interaccion
    """
    print("Returning social media metrics...")
    own = session is None
    async def _run(sess: AsyncSession):
        general = await get_social_media_general_metrics(sess)
        volumen = await get_social_media_volume_metrics(sess, total_records=general.get("total_records", 0))
        temporal = await get_social_media_temporal_metrics(sess)
        interaction = await get_social_media_interaction_metrics(sess)
        sentiment = await get_social_media_sentiment_metrics(sess)
        geography = await get_social_media_geographic_metrics(sess)
        return {
            "general": general,
            "volumen": volumen,
            "temporal": temporal,
            "interaction": interaction,
            "sentiment": sentiment,
            "geography": geography,
        }

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_geographic_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return geographic metrics aggregated by city: avg sentiment, avg interaccion, avg engagement."""
    own = session is None

    async def _run(sess: AsyncSession):
        stmt = select(
            SocialMediaRecord.ciudad,
            func.count().label("total"),
            func.avg(SocialMediaRecord.sentiment).label("avg_sentiment"),
            func.avg(SocialMediaRecord.interaccion).label("avg_interaccion"),
            func.avg(SocialMediaRecord.engagement).label("avg_engagement"),
        ).group_by(SocialMediaRecord.ciudad).order_by(func.count().desc())

        res = await sess.execute(stmt)
        by_city = []
        for r in res.fetchall():
            total = int(r.total or 0)
            by_city.append({
                "ciudad": r.ciudad,
                "total": total,
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "avg_interaccion": float(r.avg_interaccion) if r.avg_interaccion is not None else 0.0,
                "avg_engagement": float(r.avg_engagement) if r.avg_engagement is not None else 0.0,
            })

        return {"by_city": by_city}

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_interaction_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return interaction/reach metrics per network and top-10 posts by interaction."""
    own = session is None

    async def _run(sess: AsyncSession):
        # Aggregates per network
        stmt_net = select(
            SocialMediaRecord.red,
            func.coalesce(func.sum(SocialMediaRecord.interaccion), 0).label("total_interaccion"),
            func.avg(SocialMediaRecord.interaccion).label("avg_interaccion"),
            func.avg(SocialMediaRecord.engagement).label("avg_engagement"),
            func.avg(SocialMediaRecord.shares).label("avg_shares"),
            func.avg(SocialMediaRecord.likes).label("avg_likes"),
            func.avg(SocialMediaRecord.comments).label("avg_comments"),
            func.avg(SocialMediaRecord.views).label("avg_views"),
        ).group_by(SocialMediaRecord.red).order_by(func.coalesce(func.sum(SocialMediaRecord.interaccion), 0).desc())

        res_net = await sess.execute(stmt_net)
        per_network = []
        for r in res_net.fetchall():
            per_network.append({
                "red": r.red,
                "total_interaccion": float(r.total_interaccion or 0),
                "avg_interaccion": float(r.avg_interaccion) if r.avg_interaccion is not None else 0.0,
                "avg_engagement": float(r.avg_engagement) if r.avg_engagement is not None else 0.0,
                "avg_shares": float(r.avg_shares) if r.avg_shares is not None else 0.0,
                "avg_likes": float(r.avg_likes) if r.avg_likes is not None else 0.0,
                "avg_comments": float(r.avg_comments) if r.avg_comments is not None else 0.0,
                "avg_views": float(r.avg_views) if r.avg_views is not None else 0.0,
            })

        # Top 10 posts by interaccion
        stmt_top = select(
            SocialMediaRecord.id,
            SocialMediaRecord.red,
            SocialMediaRecord.user_id,
            SocialMediaRecord.username,
            SocialMediaRecord.text,
            SocialMediaRecord.interaccion,
            SocialMediaRecord.created_at,
            SocialMediaRecord.link,
            SocialMediaRecord.linkpage,
        ).order_by(func.coalesce(SocialMediaRecord.interaccion, 0).desc()).limit(10)

        res_top = await sess.execute(stmt_top)
        top_posts = []
        for r in res_top.fetchall():
            created = r.created_at
            created_iso = None
            try:
                created_iso = created.isoformat() if created is not None else None
            except Exception:
                created_iso = str(created)

            text_val = r.text
            if text_val and isinstance(text_val, str) and len(text_val) > 400:
                text_val = text_val[:400] + "..."

            top_posts.append({
                "id": r.id,
                "red": r.red,
                "user_id": r.user_id,
                "username": r.username,
                "text": text_val,
                "interaccion": float(r.interaccion) if r.interaccion is not None else 0.0,
                "created_at": created_iso,
                "link": r.link,
                "linkpage": r.linkpage,
            })

        return {"per_network": per_network, "top_posts": top_posts}

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_sentiment_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return sentiment and acceptance metrics:
    - counts and percentages Pos/Neu/Neg (overall)
    - sentiment by network (avg, counts)
    - sentiment by city
    - sentiment by type
    """
    own = session is None

    async def _run(sess: AsyncSession):
        # overall counts where sentiment is not null
        total_with_sent_stmt = select(func.count()).where(SocialMediaRecord.sentiment != None)
        res_total_with = await sess.execute(total_with_sent_stmt)
        total_with = int(res_total_with.scalar_one() or 0)

        pos_stmt = select(func.count()).where(SocialMediaRecord.sentiment == 1)
        neu_stmt = select(func.count()).where(SocialMediaRecord.sentiment == 0)
        neg_stmt = select(func.count()).where(SocialMediaRecord.sentiment == -1)
        res_pos = await sess.execute(pos_stmt)
        res_neu = await sess.execute(neu_stmt)
        res_neg = await sess.execute(neg_stmt)
        pos = int(res_pos.scalar_one() or 0)
        neu = int(res_neu.scalar_one() or 0)
        neg = int(res_neg.scalar_one() or 0)

        pct_pos = (pos / total_with * 100) if total_with else 0.0
        pct_neu = (neu / total_with * 100) if total_with else 0.0
        pct_neg = (neg / total_with * 100) if total_with else 0.0

        # sentiment by network
        stmt_net = select(
            SocialMediaRecord.red,
            func.coalesce(func.avg(SocialMediaRecord.sentiment), 0).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 0, 1), else_=0)), 0).label("neu"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
            func.count().label("total"),
        ).group_by(SocialMediaRecord.red).order_by(func.count().desc())

        res_net = await sess.execute(stmt_net)
        by_network = []
        for r in res_net.fetchall():
            total = int(r.total or 0)
            by_network.append({
                "red": r.red,
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "pos": int(r.pos or 0),
                "neu": int(r.neu or 0),
                "neg": int(r.neg or 0),
                "pct_pos": float(r.pos / total * 100) if total else 0.0,
                "pct_neu": float(r.neu / total * 100) if total else 0.0,
                "pct_neg": float(r.neg / total * 100) if total else 0.0,
            })

        # sentiment by city
        stmt_city = select(
            SocialMediaRecord.ciudad,
            func.coalesce(func.avg(SocialMediaRecord.sentiment), 0).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 0, 1), else_=0)), 0).label("neu"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
            func.count().label("total"),
        ).group_by(SocialMediaRecord.ciudad).order_by(func.count().desc())

        res_city = await sess.execute(stmt_city)
        by_city = []
        for r in res_city.fetchall():
            total = int(r.total or 0)
            by_city.append({
                "ciudad": r.ciudad,
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "pos": int(r.pos or 0),
                "neu": int(r.neu or 0),
                "neg": int(r.neg or 0),
                "pct_pos": float(r.pos / total * 100) if total else 0.0,
                "pct_neu": float(r.neu / total * 100) if total else 0.0,
                "pct_neg": float(r.neg / total * 100) if total else 0.0,
            })

        # sentiment by type
        stmt_type = select(
            SocialMediaRecord.type,
            func.coalesce(func.avg(SocialMediaRecord.sentiment), 0).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 0, 1), else_=0)), 0).label("neu"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
            func.count().label("total"),
        ).group_by(SocialMediaRecord.type).order_by(func.count().desc())

        res_type = await sess.execute(stmt_type)
        by_type = []
        for r in res_type.fetchall():
            total = int(r.total or 0)
            by_type.append({
                "type": r.type,
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "pos": int(r.pos or 0),
                "neu": int(r.neu or 0),
                "neg": int(r.neg or 0),
                "pct_pos": float(r.pos / total * 100) if total else 0.0,
                "pct_neu": float(r.neu / total * 100) if total else 0.0,
                "pct_neg": float(r.neg / total * 100) if total else 0.0,
            })

        return {
            "overall": {
                "total_with_sentiment": total_with,
                "pos": pos,
                "neu": neu,
                "neg": neg,
                "pct_pos": float(pct_pos),
                "pct_neu": float(pct_neu),
                "pct_neg": float(pct_neg),
            },
            "by_network": by_network,
            "by_city": by_city,
            "by_type": by_type,
        }

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_temporal_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return temporal metrics: counts and aggregated interaction/sentiment per day, week, month."""
    own = session is None

    async def _run(sess: AsyncSession):
        # By day
        stmt_day = select(
            cast(func.date(SocialMediaRecord.created_at), Date).label("period"),
            func.count().label("count"),
            func.coalesce(func.sum(SocialMediaRecord.interaccion), 0).label("sum_interaccion"),
            func.avg(SocialMediaRecord.sentiment).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
        ).group_by(func.date(SocialMediaRecord.created_at)).order_by(func.date(SocialMediaRecord.created_at))

        res_day = await sess.execute(stmt_day)
        by_day = []
        for r in res_day.fetchall():
            total = int(r.count or 0)
            pos = int(r.pos or 0)
            neg = int(r.neg or 0)
            acceptance = (pos - neg) / total if total > 0 else 0.0
            by_day.append({
                "period": r.period.isoformat() if r.period is not None else None,
                "count": total,
                "sum_interaccion": float(r.sum_interaccion or 0),
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "acceptance_index": float(acceptance),
            })

        # By week (use date_trunc('week', created_at))
        stmt_week = select(
            func.date_trunc("week", SocialMediaRecord.created_at).label("period"),
            func.count().label("count"),
            func.coalesce(func.sum(SocialMediaRecord.interaccion), 0).label("sum_interaccion"),
            func.avg(SocialMediaRecord.sentiment).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
        ).group_by(text("period")).order_by(text("period"))

        res_week = await sess.execute(stmt_week)
        by_week = []
        for r in res_week.fetchall():
            # period is a timestamp; convert to ISO date string
            period = r.period
            period_str = period.date().isoformat() if hasattr(period, "date") else str(period)
            total = int(r.count or 0)
            pos = int(r.pos or 0)
            neg = int(r.neg or 0)
            acceptance = (pos - neg) / total if total > 0 else 0.0
            by_week.append({
                "period": period_str,
                "count": total,
                "sum_interaccion": float(r.sum_interaccion or 0),
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "acceptance_index": float(acceptance),
            })

        # By month (date_trunc('month', created_at))
        stmt_month = select(
            func.date_trunc("month", SocialMediaRecord.created_at).label("period"),
            func.count().label("count"),
            func.coalesce(func.sum(SocialMediaRecord.interaccion), 0).label("sum_interaccion"),
            func.avg(SocialMediaRecord.sentiment).label("avg_sentiment"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == 1, 1), else_=0)), 0).label("pos"),
            func.coalesce(func.sum(case((SocialMediaRecord.sentiment == -1, 1), else_=0)), 0).label("neg"),
        ).group_by(text("period")).order_by(text("period"))

        res_month = await sess.execute(stmt_month)
        by_month = []
        for r in res_month.fetchall():
            period = r.period
            # period is a timestamp; format as YYYY-MM
            if hasattr(period, "date"):
                period_str = period.date().replace(day=1).isoformat()
            else:
                period_str = str(period)
            total = int(r.count or 0)
            pos = int(r.pos or 0)
            neg = int(r.neg or 0)
            acceptance = (pos - neg) / total if total > 0 else 0.0
            by_month.append({
                "period": period_str,
                "count": total,
                "sum_interaccion": float(r.sum_interaccion or 0),
                "avg_sentiment": float(r.avg_sentiment) if r.avg_sentiment is not None else 0.0,
                "acceptance_index": float(acceptance),
            })

        return {"by_day": by_day, "by_week": by_week, "by_month": by_month}

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_general_metrics(session: Optional[AsyncSession] = None) -> Dict[str, Any]:
    """Return general aggregated metrics (no volumen data)."""
    own = session is None

    async def _run(sess: AsyncSession):
        stmt = select(
            func.count(SocialMediaRecord.id),
            func.count(func.nullif(SocialMediaRecord.type, "")),
            func.sum(case((SocialMediaRecord.type == "Comment", 1), else_=0)),
            func.sum(case((SocialMediaRecord.type == "Tweet", 1), else_=0)),
            func.sum(case((SocialMediaRecord.type == "Post", 1), else_=0)),
            func.count(func.distinct(SocialMediaRecord.user_id)),
            func.count(func.distinct(SocialMediaRecord.red)),
            func.min(SocialMediaRecord.created_dmy),
            func.max(SocialMediaRecord.created_dmy),
            func.coalesce(func.sum(SocialMediaRecord.interaccion), 0),
            func.coalesce(func.sum(SocialMediaRecord.audiencia_interaccion), 0),
            func.avg(SocialMediaRecord.interaccion),
            func.avg(SocialMediaRecord.audiencia_interaccion),
        )

        res = await sess.execute(stmt)
        (
            total_records,
            _type_count,
            total_comments,
            total_tweets,
            total_posts,
            unique_users,
            unique_networks,
            min_date,
            max_date,
            total_interaccion,
            total_audiencia_interaccion,
            avg_interaccion,
            avg_audiencia_interaccion,
        ) = res.fetchone()

        return {
            "total_records": int(total_records or 0),
            "total_comments": int(total_comments or 0),
            "total_tweets": int(total_tweets or 0),
            "total_posts": int(total_posts or 0),
            "unique_users": int(unique_users or 0),
            "unique_networks": int(unique_networks or 0),
            "min_date": min_date.isoformat() if min_date is not None else None,
            "max_date": max_date.isoformat() if max_date is not None else None,
            "total_interaccion": float(total_interaccion or 0),
            "total_audiencia_interaccion": float(total_audiencia_interaccion or 0),
            "avg_interaccion": float(avg_interaccion) if avg_interaccion is not None else 0.0,
            "avg_audiencia_interaccion": float(avg_audiencia_interaccion) if avg_audiencia_interaccion is not None else 0.0,
        }

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)


async def get_social_media_volume_metrics(session: Optional[AsyncSession] = None, total_records: int | None = None) -> Dict[str, Any]:
    """Return volumen metrics: by_network, by_city, pct_replies, pct_retweets."""
    own = session is None

    async def _run(sess: AsyncSession):
        # posts by network
        stmt_net = select(SocialMediaRecord.red, func.count()).group_by(SocialMediaRecord.red).order_by(func.count().desc())
        res_net = await sess.execute(stmt_net)
        by_network = [{"red": r[0], "count": int(r[1])} for r in res_net.fetchall()]

        # posts by city
        stmt_city = select(SocialMediaRecord.ciudad, func.count()).group_by(SocialMediaRecord.ciudad).order_by(func.count().desc())
        res_city = await sess.execute(stmt_city)
        by_city = [{"ciudad": r[0], "count": int(r[1])} for r in res_city.fetchall()]

        # percent replies and retweets (relative to total records)
        stmt_replies = select(func.count()).where(SocialMediaRecord.is_reply == True)
        stmt_rts = select(func.count()).where(SocialMediaRecord.is_rt == True)
        res_replies = await sess.execute(stmt_replies)
        res_rts = await sess.execute(stmt_rts)
        count_replies = res_replies.scalar_one() or 0
        count_rts = res_rts.scalar_one() or 0

        tr = total_records if total_records is not None else 0
        pct_replies = (int(count_replies) / int(tr) * 100) if tr and int(tr) > 0 else 0.0
        pct_retweets = (int(count_rts) / int(tr) * 100) if tr and int(tr) > 0 else 0.0

        return {
            "by_network": by_network,
            "by_city": by_city,
            "pct_replies": float(pct_replies),
            "pct_retweets": float(pct_retweets),
        }

    if own:
        async with AsyncSessionLocal() as sess:
            return await _run(sess)
    return await _run(session)
