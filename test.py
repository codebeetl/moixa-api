import os
from dotenv import load_dotenv
from moixa_py import MoixaCognitoAuth, MoixaClient, TokenStore

load_dotenv()

auth = MoixaCognitoAuth(os.getenv('MOIXA_USERNAME'), os.getenv('MOIXA_PASSWORD'))
tokens = auth.login()
TokenStore().save(tokens)
print(f'Logged in. Access token expires in {tokens.expires_in}s.')

client = MoixaClient(tokens)
print(client.get_site_users())
