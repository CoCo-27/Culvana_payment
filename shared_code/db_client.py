import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
import os
import logging
from datetime import datetime
from typing import Optional, Dict, List
from .models import PaymentSetup, Location, Transaction, Plan, BaseModel

class CosmosDBClient:
    def __init__(self):
        self.client = cosmos_client.CosmosClient.from_connection_string(
            os.getenv('COSMOS_CONNECTION_STRING')
        )
        self.database = self.client.get_database_client('culvana')
        self.payment_container = self.database.get_container_client('culvana-payment')
        self.location_container = self.database.get_container_client('culvana-location')
        self.transaction_container = self.database.get_container_client('culvana-payment-log')

    async def create_payment_setup(self, email: str, status: str = 'pending', tokens: int = 0) -> Dict:
        """Create new payment setup"""
        payment_setup = PaymentSetup(email)
        item_dict = payment_setup.to_dict()
        item_dict['user_id'] = email
        item_dict['status'] = status
        item_dict['tokens'] = tokens
        return self.payment_container.upsert_item(item_dict)

    async def create_location(self, user_id: str, name: str, address: str) -> Dict:
        """Create new location"""
        location = Location(user_id, name, address)
        item_dict = location.to_dict()
        return self.location_container.upsert_item(item_dict)

    async def create_transaction(
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
        return self.transaction_container.upsert_item(item_dict)

    async def get_by_type_and_id(self, type_name: str, item_id: str) -> Optional[Dict]:
        """Get item by type and id"""
        if type_name == 'transaction':
            container = self.transaction_container
        elif type_name == 'payment_setup':
            container = self.payment_container
        else:
            container = self.location_container
            
        try:
            return container.read_item(item=item_id, partition_key=item_id)
        except exceptions.CosmosResourceNotFoundError:
            return None

    async def get_payment_setup(self, email: str) -> Optional[Dict]:
        """Get payment setup by email"""
        query = "SELECT * FROM c WHERE c.type = 'payment_setup' AND c.user_id = @user_id"
        parameters = [{"name": "@user_id", "value": email}]
        results = list(self.payment_container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        return results[0] if results else None

    async def cleanup_failed_setup(self, email: str, location_id: Optional[str] = None):
        """Clean up database entries when setup fails"""
        try:
            # Delete payment setup
            payment_setup = await self.get_payment_setup(email)
            if payment_setup:
                self.payment_container.delete_item(
                    item=payment_setup['id'],
                    partition_key=email
                )

            # Delete location if created
            if location_id:
                self.location_container.delete_item(
                    item=location_id,
                    partition_key=email
                )

            # Delete any pending transactions
            query = """
            SELECT * FROM c 
            WHERE c.user_id = @user_id 
            AND c.status = 'pending'
            """
            parameters = [{"name": "@user_id", "value": email}]
            transactions = list(self.transaction_container.query_items(
                query=query,
                parameters=parameters,
                enable_cross_partition_query=True
            ))
            
            for transaction in transactions:
                self.transaction_container.delete_item(
                    item=transaction['id'],
                    partition_key=email
                )
                
        except Exception as e:
            logging.error(f'Error in cleanup: {str(e)}')