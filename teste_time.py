import datetime
print(datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=-3))).strftime("%d-%m-%Y às %H:%M"))