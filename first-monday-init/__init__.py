import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta, MO

async def process_user_billing(db_client: CosmosDBClient, payment_setup):
    """Initialize billing for a user's payment setup and locations"""
    try:
        user_id = payment_setup['user_id']
        logging.info(f"Processing monthly initialization for user: {user_id}")
        
        locations = db_client.get_locations(user_id)
        
        total_usage = sum(location.get('current_period_fee', 0) for location in locations)
        previous_monthly_usage = payment_setup.get('monthly_usage', 0)
        current_pending_fee = payment_setup.get('pending_fee', 0)
        
        new_pending_fee = current_pending_fee + total_usage
        
        payment_setup.update({
            'previous_monthly_usage': previous_monthly_usage,
            'last_month_total': total_usage,
            'monthly_usage': 0,  
            'pending_fee': new_pending_fee,
            'last_billing_cycle': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.utcnow().isoformat()
        })
        
        db_client.payment_container.replace_item(
            item=payment_setup['id'],
            body=payment_setup
        )
        
        processed_locations = 0
        for location in locations:
            if location.get('is_active', False):
                current_fee = location.get('current_period_fee', 0)
                
                location.update({
                    'previous_period_fee': current_fee,
                    'current_period_fee': 0,
                    'last_billing_cycle': datetime.now(timezone.utc).isoformat(),
                    'last_billing_update': datetime.now(timezone.utc).isoformat(),
                    'updated_at': datetime.utcnow().isoformat()
                })
                
                db_client.location_container.replace_item(
                    item=location['id'],
                    body=location
                )
                processed_locations += 1
        
        return {
            "user_id": user_id,
            "previous_usage": previous_monthly_usage,
            "last_month_total": total_usage,
            "new_pending_fee": new_pending_fee,
            "locations_processed": processed_locations,
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

def is_first_monday_of_month():
    """Check if today is the first Monday of the month"""
    today = datetime.now()
    first_monday = today.replace(day=1) + relativedelta(weekday=MO(1))
    return today.date() == first_monday.date()

async def main(mytimer: func.TimerRequest) -> None:
    """Timer trigger function that runs on the first Monday of every month"""
    if not is_first_monday_of_month():
        logging.info("Not the first Monday of the month. Skipping execution.")
        return

    utc_timestamp = datetime.utcnow().isoformat()
    logging.info(f'First Monday monthly billing initialization started at: {utc_timestamp}')
    
    try:
        db_client = CosmosDBClient()
        
        query = "SELECT * FROM c WHERE c.type = 'payment_setup'"
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        logging.info(f'Found {len(payment_setups)} payment setups to process')
        
        if not payment_setups:
            logging.info('No payment setups to process')
            return
        
        results = await asyncio.gather(*[
            process_user_billing(db_client, payment_setup)
            for payment_setup in payment_setups
        ])
        
        successful = sum(1 for r in results if r['success'])
        failed = sum(1 for r in results if not r['success'])
        total_processed = len(results)
        
        logging.info(f'''
        Monthly initialization completed:
        - Total users processed: {total_processed}
        - Successful: {successful}
        - Failed: {failed}
        - Completion time: {datetime.utcnow().isoformat()}
        ''')
        
        for result in results:
            if not result['success']:
                logging.error(f"Failed to process user {result['user_id']}: {result.get('error')}")
        
    except Exception as e:
        logging.error(f'Critical error in monthly initialization: {str(e)}')
        raise 