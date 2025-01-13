# monthly-init/__init__.py
import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone

async def process_user_billing(db_client: CosmosDBClient, payment_setup):
    """Initialize billing for a user's payment setup and locations"""
    try:
        user_id = payment_setup['user_id']
        logging.info(f"Processing monthly initialization for user: {user_id}")
        
        # Get all locations for the user
        locations = db_client.get_locations(user_id)
        
        # Calculate total usage from current period
        total_usage = sum(location.get('current_period_fee', 0) for location in locations)
        
        # Store monthly usage and reset pending fee
        payment_setup['monthly_usage'] = total_usage
        payment_setup['pending_fee'] = 0
        payment_setup['updated_at'] = datetime.utcnow().isoformat()
        
        # Update payment setup
        db_client.payment_container.replace_item(
            item=payment_setup['id'],
            body=payment_setup
        )
        
        # Reset all location fees
        for location in locations:
            # Store current fee as last period fee
            location['last_period_fee'] = location.get('current_period_fee', 0)
            location['current_period_fee'] = 0
            location['last_billing_update'] = datetime.now(timezone.utc).isoformat()
            location['updated_at'] = datetime.utcnow().isoformat()
            
            # Update location
            db_client.location_container.replace_item(
                item=location['id'],
                body=location
            )
        
        logging.info(f"Successfully initialized billing for user: {user_id}")
        return {
            "user_id": user_id,
            "total_usage": total_usage,
            "locations_processed": len(locations),
            "success": True
        }
        
    except Exception as e:
        error_msg = f"Error initializing billing for {payment_setup['user_id']}: {str(e)}"
        logging.error(error_msg)
        return {
            "user_id": payment_setup['user_id'],
            "success": False,
            "error": str(e)
        }

async def main(mytimer: func.TimerRequest) -> None:
    """Timer trigger function that runs on the 1st of every month at 00:00 UTC"""
    utc_timestamp = datetime.utcnow().isoformat()
    logging.info(f'Monthly billing initialization started at: {utc_timestamp}')
    
    try:
        db_client = CosmosDBClient()
        
        # Get all payment setups
        query = "SELECT * FROM c WHERE c.type = 'payment_setup'"
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        logging.info(f'Found {len(payment_setups)} payment setups to process')
        
        if not payment_setups:
            logging.info('No payment setups to process')
            return
        
        # Process all users concurrently
        results = await asyncio.gather(*[
            process_user_billing(db_client, payment_setup)
            for payment_setup in payment_setups
        ])
        
        successful = sum(1 for r in results if r['success'])
        failed = sum(1 for r in results if not r['success'])
        
        logging.info('Monthly initialization completed:')
        logging.info(f'- Total processed: {len(results)}')
        logging.info(f'- Successful: {successful}')
        logging.info(f'- Failed: {failed}')
        
        # Log any failures in detail
        for result in results:
            if not result['success']:
                logging.error(f"Failed to process user {result['user_id']}: {result.get('error')}")
        
    except Exception as e:
        logging.error(f'Critical error in monthly initialization: {str(e)}')
        raise