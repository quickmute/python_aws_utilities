import boto3
import botocore
import datetime
import botocore.exceptions
profile = "default"
session = boto3.Session(profile_name=profile)
region = "us-east-1"
wafv2client = session.client("wafv2", region_name = region)
tokenExpire = datetime.datetime.now() + datetime.timedelta(hours = 1)

##This is the new rule statement dictionary we want to inject
##This makes everything count except Log4JRCE
expected_statement_dict = {
    'ManagedRuleGroupStatement': {
        'VendorName': 'AWS', 
        'Name': 'AWSManagedRulesKnownBadInputsRuleSet', 
        'Version': 'Version_1.6', 
        'ExcludedRules': [
            {
                'Name': 'ExploitablePaths_URIPATH'
            }, 
            {
                'Name': 'Host_localhost_HEADER'
            }, 
            {
                'Name': 'PROPFIND_METHOD'
            }
        ]
    }
}

## may have to loop both REGIONAL and CLOUDFRONT
Scope = 'REGIONAL'
targetRuleSet = 'AWSManagedRulesKnownBadInputsRuleSet'
all_web_acls = wafv2client.list_web_acls(
    Scope = Scope
)

for item in all_web_acls["WebACLs"]:
    web_acl = wafv2client.get_web_acl(
        Name = item["Name"],
        Id = item["Id"],
        Scope = Scope
    )
    this_web_acl = web_acl.get('WebACL',{})
    #unique token needed for update later
    LockToken = web_acl.get('LockToken','')
    Name = this_web_acl['Name']
    Scope = Scope
    ARN = this_web_acl['ARN'] 
    Id = this_web_acl['Id']
    DefaultAction = this_web_acl.get('DefaultAction',{})
    Description = this_web_acl['Description']+"- Updated"
    Rules = this_web_acl.get('Rules',[])
    VisibilityConfig = this_web_acl.get('VisibilityConfig',{})
    CustomResponseBodies = this_web_acl.get('CustomResponseBodies',None)
    CaptchaConfig = this_web_acl.get('CaptchaConfig',None)
    ## Find the rule that has the targetRuleSet that we want then we replace the content of statement in it
    list(filter(lambda arue: targetRuleSet in arue["Name"],Rules))[0]['Statement'] = expected_statement_dict
    
    ## create a special map to be used as argument to the update_web_acl method
    arguments = dict(
        Name = Name,
        Scope = Scope,
        Id = Id,
        DefaultAction = DefaultAction,
        Description = Description,
        Rules = Rules,
        VisibilityConfig = VisibilityConfig,
        LockToken = LockToken
    )
    ## These two arguments were causing some issue if trying to pass in empty map, 
    ##  so we just break them out here and only pass in if they are not None
    if CustomResponseBodies is not None:
        arguments['CustomResponseBodies'] = CustomResponseBodies
    if CaptchaConfig is not None:
        arguments['CaptchaConfig'] = CaptchaConfig
    
    ## We pass in arguments and unpack it, the double star unpacks the map here
    ## per documentation, if you want to update the web_acl it's immutable so 
    ## you have to pass in all arguments that you want to update
    wafv2client.update_web_acl(**arguments)
