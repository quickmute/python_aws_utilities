pageToken = ""
## get today's date 
meowmeow = datetime.date.today() 
## need to convert to string 
endDate = meowmeow.strftime("%Y-%m-%d")
## go back 7 days
startDate = (meowmeow + datetime.timedelta(days = -7)).strftime("%Y-%m-%d")
## whether or not we'll use filter below
filterOn = True
## granularity
## If you select a grandlarity that is smaller than the time range then you'll get a single time period
## For example, if you select MONTHLY and define start and end of a week then you'll get a single list of services
## But if you select DAILY and define start and end of 3 days then you'll get 3 separate list of services, one for each day
#granularity = "DAILY"
granularity = "MONTHLY"
## print header
report = "Billing report" + "\n"
## do this until pageToken is not found (hopefully run just once)
while pageToken is not None:
    arguments = dict(
        TimePeriod={
            'Start': startDate,
            'End': endDate
        },
        Granularity = granularity,
        Metrics = ["UnblendedCost"],
        GroupBy = [
            {
                "Type":"DIMENSION",
                "Key":"SERVICE"
            }
        ]
    )
    if (filterOn):
        arguments['Filter'] = {  
            "Or":[
                {
                    "Tags" : {
                        "Key": "Core",
                        "MatchOptions":[
                            "ABSENT"
                        ]
                    }
                },
                {
                    "Tags" : {
                        "Key": "Core",
                        "Values":[
                            "false"
                        ]
                    }
                }
            ]      
        }
    if (pageToken != ""):
         arguments['NextPageToken'] = pageToken
    cu = thisClient.get_cost_and_usage(**arguments)
    pageToken = cu.get("NextPageToken",None)
    ## keep track of total cost
    serviceCostTotal = 0.0
    ## drill in
    results = cu.get("ResultsByTime")
    for result in results:
        ## get time period 
        period = result.get("TimePeriod")
        periodStart = period.get("Start")
        periodEnd = period.get("End")
        report = report + periodStart + " thru " + periodEnd + "\n"
        ## drill into groups or services
        groups = result.get("Groups")
        for service in groups:
            ## get service name and then find it's metrics
            serviceName = "-".join(service.get("Keys",[]))
            if(serviceName != ""):
                ## get the amount (the unit will be same - for me it's Dollar)
                serviceCost = float(service.get("Metrics",{}).get("UnblendedCost",{}).get("Amount",0.0))
                serviceCostTotal = serviceCostTotal + serviceCost
                ## print the format
                txt = "{:60} : ${:.5f}"   
                ## ignore ones that are hundred thousandths
                if (serviceCost > 0.00001):
                    #print(txt.format(serviceName, serviceCost))
                    report = report + txt.format(serviceName, serviceCost) + "\n"
    report = report + "========================" + "\n"
    ## print total
    report = report + txt.format("Total", serviceCostTotal)
    #print(txt.format("Total", serviceCostTotal))
    ## print or send report somewhere
    print(report)
