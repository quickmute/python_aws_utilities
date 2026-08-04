from botocore.exceptions import ClientError
import boto3
import logging
import time
import random

# Set up our logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("account_closer")
max_delete = 250
profile = "default"
session = boto3.Session(profile_name=profile)
region = "us-east-1"
master_account = "999999999999"

RETRYABLE = {'TooManyRequestsException', 'ThrottlingException'}
## This is a function to handle the jiggle backoff and retry
## Note the second argument of "*" is just a divider to clarify the intent of next arguments
def with_backoff(fn, *, max_attempts=6, base=0.5, cap=30.0):
    """Call fn(); retry on transient errors with exponential backoff + jitter."""
    for attempt in range(max_attempts):
        try:
            return fn()
        except ClientError as e:
            code = e.response['Error']['Code']
            # Not retryable, or out of attempts -> give up and re-raise
            if code not in RETRYABLE or attempt == max_attempts - 1:
                raise
            # exponential: base * 2^attempt, capped, then randomized
            delay = min(cap, base * (2 ** attempt))
            delay = random.uniform(0, delay)   # "full jitter"
            logger.info(f"{code}: retry {attempt + 1}/{max_attempts} in {delay:.2f}s")
            time.sleep(delay)

 ## just a wrapper function so it returns True
def close_account(account_id):
    ## this function below has no return
    orgClient.close_account(AccountId=account_id)
    ## unless it errors out, it will return true
    return True

## paginate through list_accounts
orgClient = session.client("organizations", region_name = region)
paginator = orgClient.get_paginator('list_accounts')
active = 0
response_iterator = paginator.paginate()
limit_reached = False
for response in response_iterator:
    if limit_reached:
        break
    for account in response["Accounts"]:
        ## If it isn't active then we skip it
        if(account.get("State") != "ACTIVE"):
            continue
        ## keep track of how many active accounts we found
        account_id = account.get("Id")
        active += 1
        ## the quota is 20% or 250 accounts per 30 day window
        if (active > max_delete):
            break
        ## don't attempt to close master account
        if (account_id == master_account):
            continue
        logger.info(f"Deleting number {active}, ID {account_id}")
        try:
            ## create the function on the fly then pass in argument so that with_backoff is calling the function instead of function running by itself first
            with_backoff(lambda aid=account_id: close_account(aid))    
        ## catch this error where we reached the limit of account close for 30 day period
        except orgClient.exceptions.ConstraintViolationException as error:
            reason = error.response["Error"].get("Message", "")   # Reason text is in the message
            if "CLOSE_ACCOUNT" in reason:
                logger.info(f"Close quota reached, stopping: {error}")
                limit_reached = True
                break
            logger.warning(f"Unexpected constraint violation on {account_id}: {error}")
            raise
## get count os active and closed accounts
not_active = 0
active = 0
## call this paginator again to get new set of data
response_iterator = paginator.paginate()
for response in response_iterator:
    for account in response["Accounts"]:
        if(account.get("State") == "ACTIVE"):
            active += 1
        else:
            not_active += 1

logger.info(f"Active: {active} Not: {not_active} Total: {active + not_active}")
