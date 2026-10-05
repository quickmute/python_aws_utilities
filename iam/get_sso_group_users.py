## This script requires credential to Management Account of the Org or a delegated admin for AWS IAM Identity Center
## SSO Members Sheet ----
## This is to get all of Groups from AWS IAM Identity Center
## then get all the Users inside each Groups
## then get username of each user
## Permission Sets Sheet ---
## This provides Groups and AWS Account where it is used and with which Permission Set
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import argparse
import pandas as pd
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--profile", default="default")
    p.add_argument("--out", default="aws_sso_user_list.xlsx")
    args = p.parse_args()
    
    region = "us-east-1" ## this must be in us-east-1 since this is where we homed our Identity Center
    ##setup session in our profile and region
    try:
        session = boto3.Session(profile_name=args.profile, region_name=region)
    except BotoCoreError as err:
        raise SystemExit(f"Could not load AWS profile '{args.profile}': {err}")
    client_config = Config(retries={"mode": "adaptive", "max_attempts": 10})
    ##This client is needed to get list instances (list_instances)
    sso_admin_client = session.client('sso-admin', config=client_config)
    ##This client is needed to get groups (list_groups), get who is in groups (list_group_memberships)
    id_store_client = session.client('identitystore', config=client_config)
    ##This client is to get account id to names
    org_client = session.client("organizations", config=client_config)
    
    # Get Identity Store ID, this will be used by Identity Store Client later
    try:
        instances = sso_admin_client.list_instances()["Instances"]
    except (ClientError, BotoCoreError) as err:
        raise SystemExit(f"Failed to get instance id with {err}")
    if not instances:
        raise SystemExit(f"No Identity Center instance found in {region} for profile {args.profile}")
    instance_arn = instances[0]["InstanceArn"]
    identity_store_id = instances[0]["IdentityStoreId"]

    ## get all the account id to names resolved
    account_names = {}
    try:
        account_paginator = org_client.get_paginator('list_accounts')
        account_response_iterator = account_paginator.paginate()
        for account_response in account_response_iterator:
            for acct in account_response["Accounts"]:
                account_names[acct["Id"]] = acct["Name"]
    except ClientError as err:
        print(f"WARN: cannot read Organizations account names ({err.response['Error']['Code']}); using IDs only")
                
    ## prefetch all Users available, this makes it more efficient since boto3 is doing pagination for us
    user_dict = {}
    try:
        user_paginator = id_store_client.get_paginator('list_users')
        user_response_iterator = user_paginator.paginate(
            IdentityStoreId=identity_store_id
        )
        for user_response in user_response_iterator:
            for user in user_response["Users"]:
                user_dict[user["UserId"]] = user["UserName"]
    except (ClientError, BotoCoreError) as err:
        raise SystemExit(f"Failed to list users: {err}")            
    
    ## prefetch all the permission sets too they are re-used across multiple accounts
    ps_name_dict = {}
    try:
        perm_set_paginator = sso_admin_client.get_paginator('list_permission_sets')
        perm_set_response_iterator = perm_set_paginator.paginate(
            InstanceArn=instance_arn
        )
        for perm_set_response in perm_set_response_iterator:
            for perm_set_arn in perm_set_response["PermissionSets"]:
                resp = sso_admin_client.describe_permission_set(
                    InstanceArn=instance_arn, 
                    PermissionSetArn=perm_set_arn
                )
                ps_name_dict[perm_set_arn] = resp["PermissionSet"]["Name"]
    except (ClientError, BotoCoreError) as err:
        raise SystemExit(f"Failed to list permission sets: {err}")

    ##populate this to output later
    sso_member_report_list = []
    permission_set_report_list = []
    group_paginator = id_store_client.get_paginator('list_groups')
    group_response_iterator = group_paginator.paginate(
        IdentityStoreId=identity_store_id,
    )
    group_member_paginator = id_store_client.get_paginator('list_group_memberships')
    assignment_paginator = sso_admin_client.get_paginator('list_account_assignments_for_principal')
    try:
        for group_response in group_response_iterator:
            for group in group_response["Groups"]:
                group_id = group["GroupId"]
                display_name = group.get("DisplayName", "unknown")
                print(f"{group_id}:{display_name}")            
                group_info = {
                    "group_id": group_id,
                    "group": display_name,
                }
                ## create iterator for members in a group, will be calling this over and over again
                member_response_iterator = group_member_paginator.paginate(
                    IdentityStoreId=identity_store_id,
                    GroupId=group_id,
                )
                ## create a iterator that takes group and returns the account_id and permission_set assignment
                assignment_iterator = assignment_paginator.paginate(
                    InstanceArn=instance_arn,
                    PrincipalId=group_id,
                    PrincipalType='GROUP',
                )
                ## set a counter for members so that we know when a group is empty
                member_count = 0
                ## counter to determine an unused group
                account_count = 0
                try:
                    for member_response in member_response_iterator:
                        for member in member_response["GroupMemberships"]:
                            user_id = member['MemberId'].get('UserId')
                            if not user_id:
                                continue
                            member_count += 1
                            user_name = user_dict.get(user_id, "unknown")
                            sso_member_report_list.append({
                                **group_info, 
                                "user": user_name, 
                                "user_id": user_id
                            })
                except ClientError as err:
                    code = err.response["Error"]["Code"]
                    if code == "ResourceNotFoundException":
                        print(f"WARN: group {group_id} disappeared during run, skipping")
                        continue
                    else:
                        raise SystemExit(f"Failed to list members of {display_name} ({group_id}): {err}")
                try:                    
                    for assignment_response in assignment_iterator:
                        for assignment in assignment_response["AccountAssignments"]:                            
                            account_count += 1
                            account_id = assignment["AccountId"]
                            permission_set_arn = assignment["PermissionSetArn"]
                            account_name = account_names.get(account_id,"unknown")
                            permission_set_name = ps_name_dict.get(permission_set_arn,"unknown")
                            
                            permission_set_report_list.append({
                                **group_info, 
                                "account_name": account_name,
                                "account_id": account_id, 
                                "permission_set_name": permission_set_name,
                                "permission_set_arn": permission_set_arn,
                            })
                except ClientError as err:
                    code = err.response["Error"]["Code"]
                    if code == "ResourceNotFoundException":
                        print(f"WARN: group {group_id} disappeared during run, skipping")    
                        continue
                    else:
                        raise SystemExit(f"Failed to get association for {group_id}: {err}")
                
                if member_count == 0:                
                    sso_member_report_list.append({
                        **group_info, 
                        "user": "empty group", 
                        "user_id": ""
                    })
                if account_count == 0:
                    permission_set_report_list.append({
                        **group_info, 
                        "account_name": "unused group",
                        "account_id": "", 
                        "permission_set_name": "",
                        "permission_set_arn": "",
                    })
    except (ClientError, BotoCoreError) as err:
        raise SystemExit(f"Failed to list groups: {err}")
    sso_members_columns=["group_id", "group", "user", "user_id"]
    sso_member_data_frame = pd.DataFrame(sso_member_report_list, columns=sso_members_columns)
    permission_set_columns=["group_id", "group", "account_name", "account_id","permission_set_name","permission_set_arn"]
    permission_set_data_frame = pd.DataFrame(permission_set_report_list, columns=permission_set_columns)
    # create Excel sheet and table
    try:
        with pd.ExcelWriter(args.out, engine="openpyxl") as writer:
            sso_member_data_frame.to_excel(writer, index=False, header=True, sheet_name="AWS SSO Members")
            permission_set_data_frame.to_excel(writer, index=False, header=True, sheet_name="Permission Set Assignment")
            sso_member_worksheet = writer.sheets["AWS SSO Members"]
            if len(sso_member_data_frame):
                sso_ref = f"A1:{get_column_letter(len(sso_members_columns))}{len(sso_member_data_frame) + 1}"
                sso_table = Table(displayName="SSOMembers", ref=sso_ref)
                sso_table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
                sso_member_worksheet.add_table(sso_table)
            permission_set_worksheet = writer.sheets["Permission Set Assignment"]
            if len(permission_set_data_frame):
                ps_ref = f"A1:{get_column_letter(len(permission_set_columns))}{len(permission_set_data_frame) + 1}"
                ps_table = Table(displayName="PermissionSets", ref=ps_ref)
                ps_table.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showRowStripes=True)
                permission_set_worksheet.add_table(ps_table)
            
    except PermissionError:
        raise SystemExit(f"Cannot write {args.out}: is it open in Excel? Close it and re-run.")
    except OSError as err:
        raise SystemExit(f"Failed to write {args.out}: {err}")
    print(f"Done. Wrote to {args.out}")

if __name__ == "__main__":
    main()
