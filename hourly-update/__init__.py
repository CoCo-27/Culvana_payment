import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from shared_code import fee_update

async def main(mytimer: func.TimerRequest) -> None:
    """Timer trigger function that runs every hour"""
    try:
        logging.info('Starting hourly fee update process')
        
        # Initialize database client
        db_client = CosmosDBClient()
        
        # Query all payment setups
        query = "SELECT * FROM c WHERE c.type = 'payment_setup'"
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        # Update fees for all users
        tasks = [
            fee_update.update_user_pending_fee(db_client, payment_setup)
            for payment_setup in payment_setups
        ]
        
        # Run all updates concurrently
        await asyncio.gather(*tasks)
        
        logging.info(f'Successfully updated fees for {len(payment_setups)} users')
        
    except Exception as e:
        logging.error(f'Error in fee update process: {str(e)}')
        raise