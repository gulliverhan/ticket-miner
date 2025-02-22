import json
from pathlib import Path
from typing import Dict, Any

def save_ticket_data(ticket_data: Dict[Any, Any], ticket_id: str, file_suffix: str = "raw") -> Path:
    """Save ticket data to a JSON file in the samples directory."""
    output_dir = Path("tests/extractors/data/samples")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_file = output_dir / f"{ticket_id}_{file_suffix}.json"
    with open(output_file, "w") as f:
        json.dump(ticket_data, f, indent=2)
    return output_file

def find_ticket_in_references(ticket_id: str, ticket_data: Dict[Any, Any]) -> bool:
    """Find a ticket ID in various reference locations within the ticket data."""
    print(f"\nLooking for ticket {ticket_id} in references")

    # Check if the ticket ID matches
    if ticket_data.get('id') == ticket_id:
        print(f"Found ticket {ticket_id} as main ticket ID")
        return True
         
    # Check in references section
    references = ticket_data.get('references', {})
    jira_tickets = references.get('jira_tickets', [])
    
    # First check direct matches in jira_tickets array
    for ticket in jira_tickets:
        if isinstance(ticket, dict):
            if ticket.get('id') == ticket_id:
                print(f"Found ticket {ticket_id} in references with context: {ticket.get('context')}")
                return True
            
    # Check in issue links
    issue_links = ticket_data.get('issuelinks', [])
    for link in issue_links:
        if isinstance(link, dict):
            # Check both inward and outward issues
            if link.get('inwardIssue', {}).get('key') == ticket_id:
                print(f"Found ticket {ticket_id} in inward issue links with type: {link.get('type', {}).get('name', 'unknown')}")
                return True
            if link.get('outwardIssue', {}).get('key') == ticket_id:
                print(f"Found ticket {ticket_id} in outward issue links with type: {link.get('type', {}).get('name', 'unknown')}")
                return True

    # Check in comments
    comments = ticket_data.get('comments', [])
    for comment in comments:
        if isinstance(comment, dict) and ticket_id in comment.get('body', ''):
            print(f"Found ticket {ticket_id} in comment by {comment.get('author')} at {comment.get('created')}")
            return True

    # Check in description
    if ticket_id in ticket_data.get('description', ''):
        print(f"Found ticket {ticket_id} in ticket description")
        return True
                
    # Check in nested references
    for ticket in jira_tickets:
        if isinstance(ticket, dict) and 'references' in ticket:
            nested_found = find_ticket_in_references(ticket_id, ticket)
            if nested_found:
                return True

    print(f"Did not find ticket {ticket_id} in any reference location")
    return False

def print_ticket_analysis(ticket_data: Dict[Any, Any], analysis: Dict[Any, Any]) -> None:
    """Print key findings from ticket analysis."""
    print("\nKey findings from analysis:")
    print(f"People involved: {', '.join(analysis.get('people', []))}")
    print(f"References found: {len(analysis.get('references', []))}")
    
    # Print URLs
    urls = analysis['references']
    print("\nFound URLs:")
    for url_type, url_list in urls.items():
        print(f"\n{url_type}:")
        for url in url_list:
            print(f"  - {url}")
    
    # Print people involved
    people = analysis.get('people', {})
    print("\nPeople involved:")
    for person_id, person_data in people.items():
        print(f"\n{person_id}:")
        print(f"  Activities: {person_data['activity_types']}")
        print(f"  First seen: {person_data['first_seen']}")
        print(f"  Last seen: {person_data['last_seen']}")
        print(f"  Number of activities: {len(person_data['activities'])}") 