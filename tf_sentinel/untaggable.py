import requests
import json
import re
## call the AWS provider API
provider_API = requests.get('https://registry.terraform.io/v1/providers/hashicorp/aws')
if (provider_API.status_code == 200):
    provider_text  = json.loads(provider_API.text)
    print(provider_text['id'])
    counter = 0
    ## for debugging: set this to 0 to turn off limiter, set to > 0 to turn on
    limit = 0
    ## all the resource names have this prefix, we could also find this inside the resource text
    prefix = "aws_"
    ## create a new file
    myFile = open("untaggable.txt", "w")

    for item in provider_text['docs']:
        ## only look at resources - NOT data-sources
        if (item['category'] == 'resources'):
            ## keep item and title
            id = item['id']
            title = item['title'] 
            ## here be uri for resource
            resource_uri = 'https://registry.terraform.io/v2/provider-docs/' + id
            ## call the resource
            resource_API = requests.get(resource_uri)
            if (resource_API.status_code == 200):
                ## print(resource_API.text)
                ## get the text of resource
                resource_info = json.loads(resource_API.text)
                ## get the content which is under data --> attributes
                content = resource_info['data'].get('attributes',{}).get('content')
                ## here is the search string for tag text in the markdown text
                regex = '\`tags\`\s*-\s*\(Optional\)'
                matching = re.search(regex, content)
                if (matching is None):
                    print(id, "-" ,title)
                    myFile.write("\"" + prefix + title + "\",\n")
                counter = counter + 1
                if (counter == limit):
                    myFile.close()
                    break
    myFile.close()
