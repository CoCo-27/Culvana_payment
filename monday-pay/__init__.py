# __init__.py
import azure.functions as func
import logging
from shared_code.db_client import CosmosDBClient
import asyncio
from datetime import datetime

async def process_user_fee(db_client: CosmosDBClient, payment_setup):
    """Process pending fee deduction for a user"""
    logging.info(f"Processing payment for user: {payment_setup['user_id']}")
    
    try:
        tokens = payment_setup.get('tokens', 0)
        pending_fee = payment_setup.get('pending_fee', 0)
        
        result = {
            "user_id": payment_setup['user_id'],
            "processed_at": datetime.utcnow().isoformat(),
            "initial_tokens": tokens,
            "pending_fee": pending_fee,
            "success": False,
            "is_blocked": False,
            "message": ""
        }
        
        if pending_fee == 0:
            result.update({
                "success": True,
                "message": "No pending fee to process"
            })
            logging.info(f"No pending fee for user: {payment_setup['user_id']}")
            return result
            
        if tokens >= pending_fee:
            new_tokens = tokens - pending_fee
            
            payment_setup['tokens'] = new_tokens
            payment_setup['pending_fee'] = 0
            payment_setup['is_blocked'] = False
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )
            
            result.update({
                "success": True,
                "final_tokens": new_tokens,
                "message": f"Successfully processed payment. Remaining tokens: {new_tokens}"
            })
            logging.info(f"Successfully processed payment for user: {payment_setup['user_id']}, remaining tokens: {new_tokens}")
            return result
        else:
            payment_setup['is_blocked'] = True
            payment_setup['updated_at'] = datetime.utcnow().isoformat()
            
            db_client.payment_container.replace_item(
                item=payment_setup['id'],
                body=payment_setup
            )
            
            result.update({
                "success": False,
                "is_blocked": True,
                "message": f"Insufficient tokens for payment. Required: {pending_fee}, Available: {tokens}"
            })
            logging.warning(f"Insufficient tokens for user: {payment_setup['user_id']}, required: {pending_fee}, available: {tokens}")
            return result
            
    except Exception as e:
        error_msg = f"Error processing payment for {payment_setup['user_id']}: {str(e)}"
        logging.error(error_msg)
        result.update({
            "success": False,
            "error": str(e),
            "message": "Internal error during payment processing"
        })
        return result

async def main(mytimer: func.TimerRequest) -> None:
    """Timer trigger function that runs every Monday at 00:00 UTC"""
    utc_timestamp = datetime.utcnow().isoformat()
    logging.info(f'Monday payment processing started at: {utc_timestamp}')
    
    try:
        db_client = CosmosDBClient()
        
        query = """
        SELECT * FROM c 
        WHERE c.type = 'payment_setup' 
        AND c.pending_fee > 0
        """
        
        payment_setups = list(db_client.payment_container.query_items(
            query=query,
            enable_cross_partition_query=True
        ))
        
        logging.info(f'Found {len(payment_setups)} payments to process')
        
        if not payment_setups:
            logging.info('No pending payments to process')
            return
        
        results = await asyncio.gather(*[
            process_user_fee(db_client, payment_setup)
            for payment_setup in payment_setups
        ])
        
        successful = sum(1 for r in results if r['success'])
        blocked = sum(1 for r in results if r['is_blocked'])
        
        logging.info(f'Payment processing completed:')
        logging.info(f'- Total processed: {len(results)}')
        logging.info(f'- Successful: {successful}')
        logging.info(f'- Blocked accounts: {blocked}')
        
    except Exception as e:
        logging.error(f'Critical error in payment processing: {str(e)}')
        raise

