# shared_code/event_publisher.py
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone
from azure.eventgrid import EventGridPublisherClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import AzureError
from .constants import (
    EVENT_TYPE_THRESHOLD_EXCEEDED,
    EVENT_SUBJECT_PREFIX,
    MAX_RETRIES,
    RETRY_DELAY
)

class EventGridPublisher:
    def __init__(self):
        self.client = EventGridPublisherClient(
            endpoint=os.environ["EventGrid_TopicEndpoint"],
            credential=AzureKeyCredential(os.environ["EventGrid_TopicKey"])
        )
    
    async def publish_threshold_event(self, user_id: str, current_fee: float, threshold: float):
        event = [{
            'event_type': EVENT_TYPE_THRESHOLD_EXCEEDED,
            'subject': f'{EVENT_SUBJECT_PREFIX}/{user_id}',
            'data': {
                'userId': user_id,
                'currentFee': current_fee,
                'threshold': threshold,
                'timestamp': datetime.now(timezone.utc).isoformat()
            },
            'data_version': '1.0'
        }]
        
        for attempt in range(MAX_RETRIES):
            try:
                self.client.send(event)
                logging.info(f"Successfully published threshold event for user {user_id}")
                return True
            except AzureError as e:
                logging.error(f"Attempt {attempt + 1} failed to publish threshold event: {str(e)}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY.total_seconds() * (attempt + 1))
                else:
                    logging.error(f"Final attempt failed for user {user_id}")
                    return False
            except Exception as e:
                logging.error(f"Unexpected error publishing threshold event: {str(e)}")
                return False