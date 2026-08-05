import boto3
import botocore
import botocore.exceptions
import datetime
import logging
import json
import pandas as pd
from openpyxl import load_workbook
from openpyxl.worksheet.table import Table, TableStyleInfo

# Set up our logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("users")

audit_session = boto3.Session(profile_name="audit")
master_session = boto3.Session(profile_name="master")
region = "us-east-1"

def parse_tags(tag_dict):
    key_list = [
        "SupportContact",
        "Description",
        "BusinessContact",
        "BillingContact",
        "Application"	,
        "Environment"	,
        "Solution"
    ]
    my_dict = dict.fromkeys(key_list, "Undefined")
    for tag in tag_dict:
        key = None
        value = None
        for item in tag:
            if item == 'Key':
                ## this is Key
                key = tag[item]
            else:
                ## anything else is assumed to be the value. This can be either value or Value
                value = tag[item]
        if key in key_list:
            my_dict[key]= value
    return my_dict

def assume_thy_role(thisClient,targetAccount,targetRole,sessionName,targetService,duration=900):
    executionRole = f"arn:aws:iam::{targetAccount}:role/{targetRole}"
    try:
        logger.info(f"assume_role: {executionRole}")
        assume_role_response = thisClient.assume_role(RoleArn=executionRole, RoleSessionName=sessionName, DurationSeconds=duration)
    except Exception as err:
        logger.info(f"assume_role error: {err}")
        return None
    targetCreds = assume_role_response.get('Credentials',None)
    targetClient = boto3.client(targetService,region_name=region,
        aws_access_key_id=targetCreds['AccessKeyId'],
        aws_secret_access_key=targetCreds['SecretAccessKey'],
        aws_session_token=targetCreds['SessionToken'])
    return targetClient

def get_user_details(thisClient,username):
    my_user_details = {}
    user = thisClient.get_user(UserName=username).get("User")
    createDate = user.get('CreateDate').strftime("%Y-%m-%d")
    passwordLastUsed = user.get('PasswordLastUsed')
    if (passwordLastUsed is not None):
        passwordLastUsed = passwordLastUsed.strftime("%Y-%m-%d")
    else:
        passwordLastUsed = 'never'
    my_user_details = parse_tags(user.get('Tags'))
    my_user_details["CreateDate"] = createDate
    my_user_details["PasswordLastUsed"] = passwordLastUsed
    return my_user_details
    
def get_access_keys(thisClient,username):
    my_access_keys = {}
    counter = 0
    access_keys = thisClient.list_access_keys(UserName=username)
    for access_key in access_keys.get('AccessKeyMetadata'):
        accessKeyId = access_key.get('AccessKeyId')
        accessKeyStatus = access_key.get('Status')
        accessKeyCreateDate = access_key.get('CreateDate').strftime("%Y-%m-%d")
        accessKeyLastUsedObj = (thisClient.get_access_key_last_used(AccessKeyId=accessKeyId)).get('AccessKeyLastUsed')
        accessKeyLastUsedDate = accessKeyLastUsedObj.get('LastUsedDate')
        if (accessKeyLastUsedDate is not None):
            accessKeyLastUsedDate = accessKeyLastUsedDate.strftime("%Y-%m-%d")
        else:
            accessKeyLastUsedDate = 'never'
        accessKeyLastUsedService = accessKeyLastUsedObj.get('ServiceName')
        accessKeyLastUsedRegion = accessKeyLastUsedObj.get('Region')
        ## Populate our unique key
        my_access_keys[f"AccessKey_{counter}_ID"] = accessKeyId
        my_access_keys[f"AccessKey_{counter}_Status"] = accessKeyStatus
        my_access_keys[f"AccessKey_{counter}_CreateDate"] = accessKeyCreateDate
        my_access_keys[f"AccessKey_{counter}_LastUsedDate"] = accessKeyLastUsedDate
        my_access_keys[f"AccessKey_{counter}_LastService"] = accessKeyLastUsedService
        my_access_keys[f"AccessKey_{counter}_LastRegion"] = accessKeyLastUsedRegion
        counter += 1
    return my_access_keys

## This role is assumable as long as we are coming from ReadOnly-master
targetRoleToAssume = "AWSOrg-ReadOnly-role"

configClient = audit_session.client("config", region_name = region)
stsClient = master_session.client("sts", region_name = region)

expression = """
SELECT
  accountId,
  resourceId,
  resourceName,
  arn
WHERE
  resourceType = 'AWS::IAM::User'
""".strip()
  
paginator = configClient.get_paginator('select_aggregate_resource_config')
response_iterator = paginator.paginate(
    Expression=expression,
    ConfigurationAggregatorName='Config-org-aggregator'
)
all_list = []
for response in response_iterator:
    for result in response["Results"]:
        user_dict = {}
        result_dict = json.loads(result)
        accountId = result_dict.get("accountId")
        resourceId = result_dict.get("resourceId")
        userName = result_dict.get("resourceName")
        arn = result_dict.get("arn")
        targetClient = assume_thy_role(stsClient,accountId,targetRoleToAssume,"userlookup","iam")
        user_dict["UserName"] = userName
        user_dict["Arn"] = arn
        user_dict["AccountId"] = accountId
        logger.info(f"Looking up {userName}")
        ## Merge into this dict
        user_dict = user_dict | get_user_details(targetClient,userName) | get_access_keys(targetClient,userName)
        all_list.append(user_dict)
        
filename = "iam_users.xlsx"
df = pd.DataFrame(all_list)
with pd.ExcelWriter(filename,mode='w') as writer:  
    df.to_excel(writer,  index=False, header=True)
