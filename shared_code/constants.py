from datetime import timedelta

DEFAULT_MONTHLY_FEE = 45
DEFAULT_THRESHOLD = 100
HOURS_IN_DAY = 24
DAYS_IN_MONTH = 30

EVENT_TYPE_THRESHOLD_EXCEEDED = 'BillingThresholdExceeded'
EVENT_TYPE_BILLING_UPDATE = 'BillingUpdate'

EVENT_SUBJECT_PREFIX = '/billing/users'

MAX_RETRIES = 3
RETRY_DELAY = timedelta(seconds=2)