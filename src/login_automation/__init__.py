from urllib.parse import urlparse
from .linkedin import login_to_linkedin
from .naukri import login_to_naukri
from loguru import logger

async def handle_login_if_needed(page, url, auth_vault):
    """
    Checks if the URL matches any supported domain in the auth_vault.
    If so, extracts the credentials and runs the corresponding login script.
    """
    domain = urlparse(url).netloc.lower()
    
    # Route to LinkedIn Automation
    if "linkedin.com" in domain and "linkedin.com" in auth_vault:
        creds = auth_vault["linkedin.com"]
        if creds.get("username") and creds.get("password"):
            return await login_to_linkedin(
                page, 
                creds.get("username"), 
                creds.get("password"), 
                creds.get("email_app_password")
            )
        
    # Route to Naukri Automation
    elif "naukri.com" in domain and "naukri.com" in auth_vault:
        creds = auth_vault["naukri.com"]
        if creds.get("username") and creds.get("password"):
            return await login_to_naukri(page, creds.get("username"), creds.get("password"))
            
    # Generic Fallback for all other sites in auth_vault
    else:
        # Check if we have credentials for this domain
        for vault_domain, creds in auth_vault.items():
            if vault_domain in domain:
                if creds.get("username") and creds.get("password"):
                    from .generic import generic_login
                    return await generic_login(page, creds.get("username"), creds.get("password"), domain)
                    
        logger.debug(f"⏭️ No specific automation script or credentials found in vault for {domain}")
        return False
