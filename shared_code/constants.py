# shared_code/constants.py
from datetime import timedelta

# Billing Constants
DEFAULT_MONTHLY_FEE = 45
DEFAULT_THRESHOLD = 100
HOURS_IN_DAY = 24
DAYS_IN_MONTH = 30

# Event Types
EVENT_TYPE_THRESHOLD_EXCEEDED = 'BillingThresholdExceeded'
EVENT_TYPE_BILLING_UPDATE = 'BillingUpdate'

# Event Subjects
EVENT_SUBJECT_PREFIX = '/billing/users'

# Retry Configuration
MAX_RETRIES = 3
RETRY_DELAY = timedelta(seconds=2)