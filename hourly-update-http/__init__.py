import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone
from shared_code import fee_update  # Import the existing fee update logic

async def main(req: func.HttpRequest) -> func.HttpResponse:
    """
    HTTP trigger function for testing fee updates
    Accepts optional user_id parameter to update specific user only
    """
    try:
        logging.info('Starting fee update process via HTTP trigger')
        
        db_client = CosmosDBClient()
        
        user_id = req.params.get('user_id')
        
        if user_id:
            payment_setup = db_client.get_payment_setup(user_id)
            if not payment_setup:
                return func.HttpResponse(
                    f"Payment setup not found for user: {user_id}",
                    status_code=404
                )
                
            await fee_update.update_user_pending_fee(db_client, payment_setup)
            return func.HttpResponse(
                f"Successfully updated fees for user: {user_id}",
                status_code=200
            )
        
        else:
            query = "SELECT * FROM c WHERE c.type = 'payment_setup'"
            payment_setups = list(db_client.payment_container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            
            tasks = [
                fee_update.update_user_pending_fee(db_client, payment_setup)
                for payment_setup in payment_setups
            ]
            
            await asyncio.gather(*tasks)
            
            return func.HttpResponse(
                f"Successfully updated fees for {len(payment_setups)} users",
                status_code=200
            )
            
    except Exception as e:
        error_message = f'Error in fee update process: {str(e)}'
        logging.error(error_message)
        return func.HttpResponse(
            error_message,
            status_code=500
        )