import os
from ghreport import get_training, get_training_details
import asyncio
import pandas as pd


#results = asyncio.run(get_training_details([1372], "microsoft", "pylance-release", os.environ['GHTOKEN'], set(['jakebailey'])))
#print(pd.DataFrame(results, columns=['prompt', 'response']).to_json(orient='records'))


#get_training("microsoft", "pylance-release", os.environ['GHTOKEN'], "pylance-training.json", True, 
#             exclude_labels=['bug', 'enhancement', 'waiting for user response'], extra_members='+erictraut,joyceerhl')

get_training("microsoft", "pyright", os.environ['GHTOKEN'], "pyright.training.json", True, 
             exclude_labels=['bug', 'enhancement', 'waiting for user response'], 
             extra_members="+kieferrm,AdamYoblick,eleanorjboyd,kimadeline,judej,jakebailey,rchiodo,gramster,gvanrossum,paulacamargo25,brettcannon,karrtikr,karthiknadig,greazer,heejaechang,StellaHuang95,bschnurr,luabud,ronglums,binderjoe,cwebster-99,debonte,int19h")