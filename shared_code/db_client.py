# shared_code/db_client.py
import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
from azure.core.credentials import AzureKeyCredential
from azure.eventgrid import EventGridPublisherClient
import os
import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, List
from .models import PaymentSetup, Location, Transaction, Plan, BaseModel

class CosmosDBClient:
    def __init__(self):
        self._client = None
        self._database = None
        self._payment_container = None
        self._location_container = None
        self._transaction_container = None
        self._event_grid_client = None

    @property
    def client(self):
        if not self._client:
            self._client = cosmos_client.CosmosClient.from_connection_string(
                os.getenv('COSMOS_CONNECTION_STRING')
            )
        return self._client

    @property
    def event_grid_client(self):
        if not self._event_grid_client:
            self._event_grid_client = EventGridPublisherClient(
                endpoint=os.getenv('EVENTGRID_ENDPOINT'),
                credential=AzureKeyCredential(os.getenv('EVENTGRID_KEY'))
            )
        return self._event_grid_client

    @property
    def database(self):
        if not self._database:
            self._database = self.client.get_database_client('culvana')
        return self._database

    @property
    def payment_container(self):
        if not self._payment_container:
            self._payment_container = self.database.get_container_client('culvana-payment')
        return self._payment_container

    @property
    def location_container(self):
        if not self._location_container:
            self._location_container = self.database.get_container_client('culvana-location')
        return self._location_container

    @property
    def transaction_container(self):
        if not self._transaction_container:
            self._transaction_container = self.database.get_container_client('culvana-payment-log')
        return self._transaction_container

    async def publish_threshold_event(self, user_id: str, current_fee: float, threshold: float):
        """Publish threshold exceeded event to Event Grid"""
        try:
            event = [{
                'event_type': 'BillingThresholdExceeded',
                'subject': f'/billing/users/{user_id}',
                'data': {
                    'userId': user_id,
                    'currentFee': current_fee,
                    'threshold': threshold,
                    'timestamp': datetime.utcnow().isoformat()
                },
                'data_version': '1.0'
            }]
            
            self.event_grid_client.send(event)
            logging.info(f"Published threshold event for user {user_id}")
            
        except Exception as e:
            logging.error(f"Error publishing threshold event: {str(e)}")
            raise

    def create_payment_setup(
        self, 
        email: str, 
        status: str = 'pending', 
        tokens: int = 0, 
        stripe_customer_id: str = None,
        plan_type: str = None,
        custom_threshold: int = None,
        num_locations: int = 0,
        pending_fee: int = 0,
        payment_methods = None,
        monthly_usage: int = 0
    ) -> Dict:
        """Create new payment setup"""
        try:
            payment_setup = PaymentSetup(
                email=email,
                status=status,
                tokens=tokens,
                stripe_customer_id=stripe_customer_id,
                plan_type=plan_type,
                custom_threshold=custom_threshold,
                num_locations=num_locations,
                pending_fee=pending_fee,
                payment_methods=payment_methods,
                monthly_usage=monthly_usage
            )
            item_dict = payment_setup.to_dict()
            item_dict['updated_at'] = datetime.utcnow().isoformat()
            
            logging.info(f"Creating payment setup: {item_dict}")
            return self.payment_container.upsert_item(body=item_dict)

        except Exception as e:
            logging.error(f"Error creating payment setup: {str(e)}")
            raise

    def create_transaction(
        self, 
        user_id: str,
        amount: int,
        transaction_type: str,
        location_id: Optional[str] = None,
        tokens: int = 0,
        status: str = 'pending',
        stripe_session_id: Optional[str] = None
    ) -> Dict:
        """Create new transaction"""
        try:
            transaction = Transaction(
                user_id=user_id,
                amount=amount,
                transaction_type=transaction_type,
                location_id=location_id,
                tokens=tokens,
                status=status,
                stripe_session_id=stripe_session_id
            )
            item_dict = transaction.to_dict()
            logging.info(f"Creating transaction: {item_dict}")
            return self.transaction_container.upsert_item(body=item_dict)

        except Exception as e:
            logging.error(f"Error creating transaction: {str(e)}")
            raise

    def create_location(
        self,
        user_id: str,
        name: str,
        address: str
    ) -> Dict:
        """Create new location"""
        try:
            location = Location(user_id, name, address)
            item_dict = location.to_dict()
            return self.location_container.upsert_item(body=item_dict)
        except Exception as e:
            logging.error(f"Error creating location: {str(e)}")
            raise

    def get_payment_setup(self, email: str) -> Optional[Dict]:
        """Get payment setup by email"""
        try:
            query = "SELECT * FROM c WHERE c.type = 'payment_setup' AND c.user_id = @user_id"
            parameters = [{"name": "@user_id", "value": email}]
            results = list(self.payment_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            return results[0] if results else None
        except Exception as e:
            logging.error(f"Error getting payment setup: {str(e)}")
            raise

    def get_payment_log(self, email: str) -> Optional[Dict]:
        """Get payment setup by email"""
        try:
            query = "SELECT * FROM c WHERE c.type = 'transaction' AND c.user_id = @user_id"
            parameters = [{"name": "@user_id", "value": email}]
            results = list(self.transaction_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            return results if results else None
        except Exception as e:
            logging.error(f"Error getting payment setup: {str(e)}")
            raise

    def get_locations(self, email: str) -> List[Dict]:
        """Get all locations for a user"""
        try:
            query = "SELECT * FROM c WHERE c.type = 'location' AND c.user_id = @user_id"
            parameters = [{"name": "@user_id", "value": email}]
            results = list(self.location_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            return results
        except Exception as e:
            logging.error(f"Error getting locations: {str(e)}")
            raise

    def update_tokens(self, email: str, tokens: int):
        """Update tokens for a user's payment setup."""
        payment_setup = self.get_payment_setup(email)
        if not payment_setup:
            raise ValueError("Payment setup not found")
        
        payment_setup['tokens'] = tokens
        payment_setup['updated_at'] = datetime.utcnow().isoformat()
        
        return self.payment_container.replace_item(
            item=payment_setup['id'],
            body=payment_setup
        )

    def get_active_locations(self) -> List[Dict]:
        """Get all active locations"""
        try:
            query = "SELECT * FROM c WHERE c.type = 'location' AND c.is_active = true"
            results = list(self.location_container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            return results
        except Exception as e:
            logging.error(f"Error getting active locations: {str(e)}")
            raise

    async def update_location_billing(self, location_id: str, current_period_fee: float, last_billing_update: str):
        """Update location billing information"""
        try:
            query = "SELECT * FROM c WHERE c.id = @id"
            parameters = [{"name": "@id", "value": location_id}]
            results = list(self.location_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            
            if not results:
                raise ValueError(f"Location {location_id} not found")
            location = results[0]
            location['current_period_fee'] = current_period_fee
            location['last_billing_update'] = last_billing_update
            location['updated_at'] = datetime.utcnow().isoformat()
            
            # Update the location
            updated_location = self.location_container.replace_item(
                item=location['id'],
                body=location
            )

        except Exception as e:
            logging.error(f"Error updating location billing: {str(e)}")
            raise

    async def update_payment_setup_pending_fee(self, email: str, pending_fee: float):
        """Update pending fee in payment setup"""
        try:
            payment_setup = self.get_payment_setup(email)
            if not payment_setup:
                raise ValueError(f"Payment setup for {email} not found")
            
            payment_setup['pending_fee'] = pending_fee
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            return self.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )
        except Exception as e:
            logging.error(f"Error updating payment setup pending fee: {str(e)}")
            raise