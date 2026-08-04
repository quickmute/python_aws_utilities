## This script is a cleanup script that removes lambda layer version permissions when Terraform is complaining about them already existing
## Alternative to doing import
## Use the Error output to target only the ones that Terraform is complaining about

import re
import boto3

profile = "default"
session = boto3.Session(profile_name=profile)

## grab the entire error output from terraform run that says this over and over again, paste it into a text file
'''
Error: adding Lambda Layer Version Permission (arn:aws:lambda:us-east-1:999999999999:layer:lib-xyz-py-requests_2_34_2-v1,1): operation error Lambda: AddLayerVersionPermission, https response error StatusCode: 409, RequestID: d32a4a60-xycx-4242-b408-d79249368b37, ResourceConflictException: The statement id (org-wide-share) provided already exists. Please provide a new statement id, or remove the existing statement.
with module.tools_init.module.s3_lambda_layer.module.lambda_layer["lib-xyz-py-requests_2_34_2-v1"].aws_lambda_layer_version_permission.lambda_layer_permission
on .terraform/modules/tools_init.s3_lambda_layer.lambda_layer/permission.tf line 3, in resource "aws_lambda_layer_version_permission" "lambda_layer_permission":
resource "aws_lambda_layer_version_permission" "lambda_layer_permission" {
'''
filecontent = open("error_output.txt","r")
line = filecontent.readline()
while line:
    ## regex to find the arn of the layer and the version, the r in front of regex expression tells Python to read it as raw string
    result = re.search(r'\(arn:aws:lambda:[^)]*\)',line)
    if(result != None):
        ## if found then snag 2 pieces of information
        layerInfo = line[result.start()+1:result.end()-1].split(",")
        ## find the region
        region = layerInfo[0].split(":")[3]
        ## create a new client for this region
        client = session.client("lambda", region_name = region)        
        ## just to get status of run
        print (layerInfo[0],layerInfo[1],region)
        ## delete the layer permission
        response = client.remove_layer_version_permission(
           LayerName=layerInfo[0],
            VersionNumber=int(layerInfo[1]),
            StatementId='org-wide-share'
        )
    ## move to next line
    line = filecontent.readline()
## close the file
filecontent.close()
