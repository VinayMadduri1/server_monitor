METRICS = ("cpu", "memory", "disk")


def get_thresholds(conn):
    return {row["metric"]: row["value"] for row in conn.execute("SELECT metric, value FROM thresholds")}


def check_thresholds(conn, sample, cooldown=300):
    """Create an alert for every metric above its threshold.

    To avoid flooding, a new alert for a metric is skipped while an
    unacknowledged alert for the same metric exists within `cooldown` seconds.
    Returns the list of alert messages created.
    """
    created = []
    thresholds = get_thresholds(conn)
    for metric in METRICS:
        limit = thresholds.get(metric)
        value = sample[metric]
        if limit is None or value <= limit:
            continue
        recent = conn.execute(
            "SELECT 1 FROM alerts WHERE metric = ? AND acknowledged = 0 AND ts > ?",
            (metric, sample["ts"] - cooldown),
        ).fetchone()
        if recent:
            continue
        message = f"{metric.upper()} usage {value:.1f}% exceeded threshold {limit:.1f}%"
        conn.execute(
            "INSERT INTO alerts (ts, metric, value, threshold, message) VALUES (?, ?, ?, ?, ?)",
            (sample["ts"], metric, value, limit, message),
        )
        created.append(message)
    return created
