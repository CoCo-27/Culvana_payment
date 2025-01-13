# monthly-init/__init__.py
import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime, timezone
import json

async def process_user_billing(db_client: CosmosDBClient, payment_setup):
    """Initialize billing for a user's payment setup and locations"""
    try:
        user_id = payment_setup['user_id']
        logging.info(f"Processing monthly initialization for user: {user_id}")
        
        # Get all locations for the user
        locations = db_client.get_locations(user_id)
        
        # Calculate total usage from current period
        total_usage = sum(location.get('current_period_fee', 0) for location in locations)
        
        # Store the current monthly values before reset
        payment_setup['last_monthly_usage'] = payment_setup.get('monthly_usage', 0)
        payment_setup['monthly_usage'] = total_usage
        payment_setup['pending_fee'] = 0
        payment_setup['updated_at'] = datetime.utcnow().isoformat()
        
        # Update payment setup
        db_client.payment_container.replace_item(
            item=payment_setup['id'],
            body=payment_setup
        )
        
        # Reset all location fees
        processed_locations = 0
        for location in locations:
            if location.get('is_active', False):
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
                processed_locations += 1
        
        logging.info(f"Successfully initialized billing for user: {user_id}, "
                    f"total_usage: {total_usage}, locations: {processed_locations}")
        return {
            "user_id": user_id,
            "total_usage": total_usage,
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

async def main(req: func.HttpRequest) -> func.HttpResponse:
    """HTTP trigger function for monthly billing initialization"""
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
            return func.HttpResponse(
                json.dumps({
                    "message": "No payment setups to process",
                    "timestamp": utc_timestamp
                }),
                mimetype="application/json",
                status_code=200
            )
        
        # Process all users concurrently
        results = await asyncio.gather(*[
            process_user_billing(db_client, payment_setup)
            for payment_setup in payment_setups
        ])
        
        successful = sum(1 for r in results if r['success'])
        failed = sum(1 for r in results if not r['success'])
        
        # Calculate total usage across all users
        total_usage = sum(r['total_usage'] for r in results if r['success'])
        total_locations = sum(r['locations_processed'] for r in results if r['success'])
        
        response = {
            'timestamp': utc_timestamp,
            'total_processed': len(results),
            'successful': successful,
            'failed': failed,
            'total_usage_processed': total_usage,
            'total_locations_processed': total_locations,
            'details': results
        }
        
        # Log summary
        logging.info(f"Monthly initialization completed: "
                    f"Processed {len(results)} users, "
                    f"Success: {successful}, "
                    f"Failed: {failed}, "
                    f"Total Usage: {total_usage}, "
                    f"Locations: {total_locations}")
        
        status_code = 200 if failed == 0 else 207  # Use 207 Multi-Status if some operations failed
        
        return func.HttpResponse(
            json.dumps(response),
            mimetype="application/json",
            status_code=status_code
        )
        
    except Exception as e:
        logging.error(f'Critical error in monthly initialization: {str(e)}')
        return func.HttpResponse(
            json.dumps({
                "error": str(e),
                "timestamp": utc_timestamp
            }),
            mimetype="application/json",
            status_code=500
        )