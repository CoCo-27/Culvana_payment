from datetime import datetime, timezone
import logging

def calculate_hourly_rate(monthly_fee: int) -> float:
    """Calculate hourly rate from monthly fee"""
    return (monthly_fee / 30) / 24

def calculate_hours_since_last_update(last_update: str) -> float:
    """Calculate hours elapsed since last billing update"""
    try:
        last_update_time = datetime.fromisoformat(last_update.replace('Z', '+00:00'))
        current_time = datetime.now(timezone.utc)
        delta = current_time - last_update_time
        return delta.total_seconds() / 3600
    except Exception as e:
        logging.error(f"Error calculating hours: {str(e)}")
        return 1.0

def should_notify_user(current_fee: float, threshold: float, last_notification_time: str = None) -> bool:
    """Determine if user should be notified based on threshold and last notification time"""
    if current_fee <= threshold:
        return False
        
    if not last_notification_time:
        return True
        
    last_notification = datetime.fromisoformat(last_notification_time.replace('Z', '+00:00'))
    hours_since_notification = (datetime.now(timezone.utc) - last_notification).total_seconds() / 3600
    return hours_since_notification >= 24