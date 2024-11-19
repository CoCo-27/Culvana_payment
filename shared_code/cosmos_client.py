import azure.cosmos.cosmos_client as cosmos_client
import azure.cosmos.exceptions as exceptions
from azure.cosmos.partition_key import PartitionKey
import os
from datetime import datetime
from typing import Optional, Dict

class CosmosClient:
    def __init__(self):
        self.client = cosmos_client.CosmosClient.from_connection_string(
            os.environ['COSMOS_CONNECTION_STRING']
        )
        self.database = self.client.get_database_client(
            os.environ['COSMOS_DATABASE_NAME']
        )
        self.container = self.database.get_container_client(
            os.environ['COSMOS_CONTAINER_NAME']
        )

    async def create_payment_setup(self, data: Dict) -> Dict:
        """Create initial payment setup with tokens"""
        document = {
            'id': f"pay_{datetime.utcnow().timestamp()}",
            'type': 'payment_setup',
            **data
        }
        return self.container.create_item(body=document)

    async def create_location(self, data: Dict) -> Dict:
        """Create new location"""
        document = {
            'id': f"loc_{datetime.utcnow().timestamp()}",
            'type': 'location',
            **data
        }
        return self.container.create_item(body=document)

    async def add_credits(self, user_id: str, amount: int) -> Dict:
        """Add one-time credits to user"""
        query = "SELECT * FROM c WHERE c.type = 'payment_setup' AND c.user_id = @user_id"
        parameters = [{"name": "@user_id", "value": user_id}]
        
        items = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        
        if items:
            payment_setup = items[0]
            payment_setup['tokens'] = payment_setup.get('tokens', 0) + amount
            payment_setup['updated_at'] = str(datetime.utcnow())
            return self.container.upsert_item(body=payment_setup)
        
        return None

    async def get_user_setup(self, user_id: str) -> Optional[Dict]:
        """Get user's payment setup"""
        query = "SELECT * FROM c WHERE c.type = 'payment_setup' AND c.user_id = @user_id"
        parameters = [{"name": "@user_id", "value": user_id}]
        
        items = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        return items[0] if items else None

    async def get_location(self, location_id: str) -> Optional[Dict]:
        """Get location details"""
        query = "SELECT * FROM c WHERE c.type = 'location' AND c.id = @id"
        parameters = [{"name": "@id", "value": location_id}]
        
        items = list(self.container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True
        ))
        return items[0] if items else None