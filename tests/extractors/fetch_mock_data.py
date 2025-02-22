import os
import json
from atlassian import Jira
from datetime import datetime
from ticket_extractors.config import JIRA_URL, JIRA_USERNAME, JIRA_API_TOKEN

def fetch_ticket_data(jira, ticket_id, processed_tickets=None):
    """
    Recursively fetch a ticket and its Jira references only.
    Ignores Confluence pages and other external references.
    
    Args:
        jira: Jira client instance
        ticket_id: ID of the ticket to fetch
        processed_tickets: Set of already processed ticket IDs
    
    Returns:
        Dict containing the raw Jira API responses
    """
    if processed_tickets is None:
        processed_tickets = set()
    
    if ticket_id in processed_tickets:
        return None
    
    processed_tickets.add(ticket_id)
    
    try:
        # Get only the essential ticket data
        issue = jira.issue(ticket_id)
        essential_fields = {
            'key': issue['key'],
            'fields': {
                'summary': issue['fields']['summary'],
                'description': issue['fields']['description'],
                'status': issue['fields']['status'],
                'created': issue['fields']['created'],
                'updated': issue['fields']['updated'],
                'priority': issue['fields'].get('priority', {'name': 'None'}),
                'assignee': issue['fields'].get('assignee', {'displayName': 'Unassigned'}),
                'reporter': issue['fields'].get('reporter', {'displayName': 'Unknown'}),
                'labels': issue['fields'].get('labels', []),
                'issuelinks': issue['fields'].get('issuelinks', [])
            }
        }
        
        # Get only essential comment data
        comments = jira.issue_get_comments(ticket_id)
        essential_comments = []
        
        if isinstance(comments, dict) and 'comments' in comments:
            comments = comments['comments']
            
        for comment in comments:
            essential_comments.append({
                'id': comment['id'],
                'body': comment['body'],
                'author': comment['author'],
                'created': comment['created']
            })
            
        essential_fields['fields']['comment'] = {'comments': essential_comments}
        
        return essential_fields
        
    except Exception as e:
        print(f"Failed to fetch ticket {ticket_id}: {str(e)}")
        return None

def main():
    # Initialize Jira client
    jira = Jira(
        url=JIRA_URL,
        username=JIRA_USERNAME,
        password=JIRA_API_TOKEN
    )
    
    # Fetch the ticket and its references
    ticket_id = "GOS-13331"
    data = fetch_ticket_data(jira, ticket_id)
    
    if data:
        # Save to a file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_file = f"tests/extractors/mock_data/ticket_{ticket_id}_{timestamp}.json"
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Saved mock data to {output_file}")
    else:
        print(f"Failed to fetch ticket {ticket_id}")

if __name__ == '__main__':
    main() 