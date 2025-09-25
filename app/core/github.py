import jwt
import time
import httpx
from typing import Optional, Dict, Any
from cryptography.hazmat.primitives import serialization
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class GitHubAppAuth:
    """Handles GitHub App authentication and token generation"""
    
    def __init__(self):
        self.app_id = settings.GITHUB_APP_ID
        self.private_key_path = settings.GITHUB_PRIVATE_KEY_PATH
        self._private_key = None
        self._installation_tokens = {}  # Cache for installation tokens
    
    def _load_private_key(self) -> bytes:
        """Load the private key from environment variable or file"""
        if self._private_key is None:
            # Try environment variable first (for Railway deployment)
            if settings.GITHUB_PRIVATE_KEY:
                logger.info("Loading private key from environment variable")
                # Convert \n back to actual newlines
                private_key_content = settings.GITHUB_PRIVATE_KEY.replace('\\n', '\n')
                self._private_key = private_key_content.encode('utf-8')
            else:
                # Fallback to file (for local development)
                try:
                    logger.info(f"Loading private key from file: {self.private_key_path}")
                    with open(self.private_key_path, 'rb') as key_file:
                        self._private_key = key_file.read()
                except FileNotFoundError:
                    logger.error(f"Private key file not found: {self.private_key_path}")
                    logger.error("Set GITHUB_PRIVATE_KEY environment variable for Railway deployment")
                    raise
        return self._private_key
    
    def generate_app_token(self) -> str:
        """Generate a JWT token for the GitHub App"""
        now = int(time.time())
        payload = {
            'iat': now - 60,  # Issued at time (1 minute ago for clock skew)
            'exp': now + 600,  # Expires in 10 minutes
            'iss': self.app_id  # Issuer (App ID)
        }
        
        private_key = serialization.load_pem_private_key(
            self._load_private_key(),
            password=None
        )
        
        token = jwt.encode(payload, private_key, algorithm='RS256')
        return token
    
    async def get_installation_token(self, installation_id: str) -> str:
        """Get an installation access token for a specific installation"""
        # Check cache first
        if installation_id in self._installation_tokens:
            token_data = self._installation_tokens[installation_id]
            if token_data['expires_at'] > time.time() + 60:  # 1 minute buffer
                return token_data['token']
        
        # Generate new token
        app_token = self.generate_app_token()
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_token}",
                    "Accept": "application/vnd.github.v3+json"
                }
            )
            
            if response.status_code != 201:
                logger.error(f"Failed to get installation token: {response.text}")
                raise Exception(f"Failed to get installation token: {response.status_code}")
            
            token_data = response.json()
            
            # Cache the token
            self._installation_tokens[installation_id] = {
                'token': token_data['token'],
                'expires_at': time.time() + 3600  # GitHub tokens expire in 1 hour
            }
            
            return token_data['token']

class GitHubAPI:
    """GitHub API client for making authenticated requests"""
    
    def __init__(self, auth: GitHubAppAuth):
        self.auth = auth
        self.base_url = "https://api.github.com"
    
    async def get_installation_token(self, installation_id: str) -> str:
        """Get installation token"""
        return await self.auth.get_installation_token(installation_id)
    
    async def make_request(
        self,
        method: str,
        endpoint: str,
        installation_id: str,
        data: Optional[Dict[Any, Any]] = None,
        params: Optional[Dict[str, str]] = None
    ) -> httpx.Response:
        """Make an authenticated request to GitHub API"""
        token = await self.get_installation_token(installation_id)
        
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "CI-Sage/1.0"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                json=data,
                params=params
            )
            
            if response.status_code >= 400:
                logger.error(f"GitHub API error: {response.status_code} - {response.text}")
            
            return response
    
    async def get_workflow_run_logs(self, installation_id: str, owner: str, repo: str, run_id: int) -> str:
        """Get workflow run logs"""
        response = await self.make_request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/logs",
            installation_id
        )
        
        if response.status_code == 200:
            return response.text
        elif response.status_code == 302:
            # GitHub returns a redirect to a signed URL for logs
            logger.info("GitHub returned redirect for logs - following redirect")
            redirect_url = response.headers.get('Location')
            if redirect_url:
                # Make a direct request to the redirect URL
                async with httpx.AsyncClient() as client:
                    redirect_response = await client.get(redirect_url)
                    if redirect_response.status_code == 200:
                        logger.info(f"Successfully fetched logs from redirect URL: {len(redirect_response.text)} characters")
                        return redirect_response.text
                    else:
                        logger.error(f"Failed to fetch logs from redirect URL: {redirect_response.status_code}")
                        return ""
            else:
                logger.error("No redirect URL found in 302 response")
                return ""
        else:
            logger.error(f"Failed to get workflow logs: {response.status_code}")
            return ""
    
    async def get_workflow_run_artifacts(self, installation_id: str, owner: str, repo: str, run_id: int) -> list:
        """Get workflow run artifacts"""
        response = await self.make_request(
            "GET",
            f"/repos/{owner}/{repo}/actions/runs/{run_id}/artifacts",
            installation_id
        )
        
        if response.status_code == 200:
            return response.json().get('artifacts', [])
        else:
            logger.error(f"Failed to get workflow artifacts: {response.status_code}")
            return []
    
    async def create_check_run(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        name: str,
        head_sha: str,
        status: str,
        conclusion: Optional[str] = None,
        output: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Create a check run"""
        data = {
            "name": name,
            "head_sha": head_sha,
            "status": status,
            "started_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        }
        
        if conclusion:
            data["conclusion"] = conclusion
            data["completed_at"] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        
        if output:
            data["output"] = output
        
        response = await self.make_request(
            "POST",
            f"/repos/{owner}/{repo}/check-runs",
            installation_id,
            data=data
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            logger.error(f"Failed to create check run: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create check run: {response.status_code}")
    
    async def create_issue(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        title: str,
        body: str,
        labels: Optional[list] = None
    ) -> Dict[str, Any]:
        """Create an issue"""
        data = {
            "title": title,
            "body": body
        }
        
        if labels:
            data["labels"] = labels
        
        response = await self.make_request(
            "POST",
            f"/repos/{owner}/{repo}/issues",
            installation_id,
            data=data
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            logger.error(f"Failed to create issue: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create issue: {response.status_code}")
    
    async def create_pull_request(
        self,
        installation_id: str,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str
    ) -> Dict[str, Any]:
        """Create a pull request"""
        data = {
            "title": title,
            "head": head,
            "base": base,
            "body": body
        }
        
        response = await self.make_request(
            "POST",
            f"/repos/{owner}/{repo}/pulls",
            installation_id,
            data=data
        )
        
        if response.status_code == 201:
            return response.json()
        else:
            logger.error(f"Failed to create pull request: {response.status_code} - {response.text}")
            raise Exception(f"Failed to create pull request: {response.status_code}")

# Global instances
github_auth = GitHubAppAuth()
github_api = GitHubAPI(github_auth)
