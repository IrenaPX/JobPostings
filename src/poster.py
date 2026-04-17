"""
poster.py
Posts the drafted content to LinkedIn using the LinkedIn Share API.

Prerequisites:
  - A LinkedIn Developer App with r_liteprofile + w_member_social scopes
    - An OAuth 2.0 access token stored as LINKEDIN_ACCESS_TOKEN in GitHub Secrets
        (LinkedIn tokens expire after 60 days — see README for refresh instructions)
        """

import os
import requests
import logging

logger = logging.getLogger(__name__)

LINKEDIN_API_BASE = "https://api.linkedin.com/v2"


def get_linkedin_person_urn() -> str:
      """
          Fetches the authenticated user's LinkedIn URN (urn:li:person:{id}).
              Required for the ugcPosts author field.
                  """
      token = os.environ["LINKEDIN_ACCESS_TOKEN"]
      headers = {
          "Authorization": f"Bearer {token}",
          "LinkedIn-Version": "202304",
      }
      response = requests.get(
          f"{LINKEDIN_API_BASE}/userinfo",
          headers=headers,
          timeout=10,
      )
      response.raise_for_status()
      data = response.json()
      sub = data.get("sub")  # OpenID Connect subject = LinkedIn member ID
    if not sub:
              raise ValueError(f"Could not extract person ID from LinkedIn userinfo: {data}")
          return f"urn:li:person:{sub}"


def post_to_linkedin(post_text: str) -> dict:
      """
          Publishes post_text as a LinkedIn share on the authenticated user's profile.
              Returns the API response dict.
                  """
      token = os.environ["LINKEDIN_ACCESS_TOKEN"]
      person_urn = get_linkedin_person_urn()

    headers = {
              "Authorization": f"Bearer {token}",
              "Content-Type": "application/json",
              "LinkedIn-Version": "202304",
              "X-Restli-Protocol-Version": "2.0.0",
    }

    payload = {
              "author": person_urn,
              "lifecycleState": "PUBLISHED",
              "specificContent": {
                            "com.linkedin.ugc.ShareContent": {
                                              "shareCommentary": {
                                                                    "text": post_text
                                              },
                                              "shareMediaCategory": "NONE"
                            }
              },
              "visibility": {
                            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
              }
    }

    response = requests.post(
              f"{LINKEDIN_API_BASE}/ugcPosts",
              headers=headers,
              json=payload,
              timeout=15,
    )
    response.raise_for_status()

    post_id = response.headers.get("X-RestLi-Id", "unknown")
    logger.info(f"LinkedIn post published successfully. Post ID: {post_id}")
    return {"post_id": post_id, "status": response.status_code}


if __name__ == "__main__":
      logging.basicConfig(level=logging.INFO)
      # Test with a sample post (requires valid LINKEDIN_ACCESS_TOKEN in env)
      test_post = "Test post from the Walmart Jobs Bot. Ignore this."
      result = post_to_linkedin(test_post)
      print(f"Result: {result}")
