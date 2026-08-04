import boto3
import time

active = 0
master_account = "999999999999"
max_delete = 250
profile = "default"
session = boto3.Session(profile_name=profile)
region = "us-east-1"
accounts_list = []
orgClient = session.client("organizations", region_name = region)
paginator = orgClient.get_paginator('list_accounts')
response_iterator = paginator.paginate()
for response in response_iterator:
    for account in response["Accounts"]:
        id = account.get("Id")
        if(account.get("State") == "ACTIVE"):
            active = active + 1
        ## the quota is 20% or 250 accounts per 30 day window
        if (active < max_delete):        
            ## don't attempt to close master account
            if (id == master_account):
                continue
            print(f"Deleting number {active}, ID {id}")
            response = orgClient.close_account(AccountId=id)
            ## this sleep prevents going over too many attempts in a time 
            print("Sleep for 10 seconds")
            time.sleep(10)
closed = 0
active = 0
for response in response_iterator:
    for account in response["Accounts"]:
        if(account.get("State") == "CLOSED"):
            closed = closed + 1
        if(account.get("State") == "ACTIVE"):
            active = active + 1

print(f"Closed: {closed}, Open: {active}")




