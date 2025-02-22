import logging
from typing import Dict, List, Set, Optional, Union
from dataclasses import dataclass
from datetime import datetime
import json
import os

# Set up logging
logger = logging.getLogger(__name__)

@dataclass
class PersonActivity:
    """Represents a person's activity in a ticket."""
    person_id: str  # Full name as returned by Jira (e.g., "John Smith")
    activity_type: str  # 'comment_author', 'assignee', 'reporter'
    ticket_id: str
    timestamp: str
    details: Dict  # Additional context about the activity

class PersonAnalyzer:
    def __init__(self, support_team_file: Optional[str] = None):
        """
        Initialize the PersonAnalyzer.
        
        Args:
            support_team_file: Optional path to a JSON file containing support team members.
                             If provided, will track team member activities separately.
        """
        self.people_database = {
            'people': {},  # Dictionary of person_id (full name) -> activities
            'statistics': {
                'total_activities': 0,
                'by_activity_type': {},
                'tickets_analyzed': set()
            }
        }
        
        self._team_members = set()
        self._has_team_config = False
        
        if support_team_file:
            try:
                with open(support_team_file, 'r') as f:
                    config = json.load(f)
                    self._team_members = set(config.get('support_team', []))
                    self._has_team_config = True
            except Exception as e:
                logger.debug(f"Could not load support team file: {e}")
                # Silently continue if file can't be loaded
                pass

    @property
    def has_team_config(self) -> bool:
        """Check if team member tracking is configured."""
        return self._has_team_config

    def is_team_member(self, full_name: str) -> bool:
        """Check if a person is a team member."""
        if not self._has_team_config:
            return False
        return full_name in self._team_members

    def analyze_ticket(self, ticket_data: Dict) -> None:
        """Analyze a ticket for person activities."""
        ticket_id = ticket_data['id']
        logger.info(f"Analyzing people in ticket: {ticket_id}")
        
        # Track that we've analyzed this ticket
        self.people_database['statistics']['tickets_analyzed'].add(ticket_id)
        
        # Record assignee activity
        if ticket_data.get('assignee'):
            self._record_activity(
                person_id=ticket_data['assignee'],
                activity_type='assignee',
                ticket_id=ticket_id,
                timestamp=ticket_data['updated'],
                details={'action': 'assigned_to_ticket'}
            )
        
        # Record reporter activity
        if ticket_data.get('reporter'):
            self._record_activity(
                person_id=ticket_data['reporter'],
                activity_type='reporter',
                ticket_id=ticket_id,
                timestamp=ticket_data['created'],
                details={'action': 'created_ticket'}
            )
        
        # Record comment activities
        for comment in ticket_data.get('comments', []):
            if comment.get('author'):
                self._record_activity(
                    person_id=comment['author'],
                    activity_type='comment_author',
                    ticket_id=ticket_id,
                    timestamp=comment['created'],
                    details={
                        'action': 'wrote_comment',
                        'comment_id': str(comment.get('id', '')),
                        'comment_preview': comment.get('body', '')[:100] if comment.get('body') else ''
                    }
                )

    def _record_activity(self, person_id: str, activity_type: str, ticket_id: str, 
                        timestamp: str, details: Dict) -> None:
        """Record a person's activity."""
        activity = PersonActivity(
            person_id=person_id,
            activity_type=activity_type,
            ticket_id=ticket_id,
            timestamp=timestamp,
            details=details
        )
        
        # Initialize person's record if not exists
        if person_id not in self.people_database['people']:
            self.people_database['people'][person_id] = {
                'activities': [],
                'first_seen': timestamp,
                'last_seen': timestamp,
                'activity_types': set(),
                'tickets_involved': set()
            }
        
        # Update person's record
        person_record = self.people_database['people'][person_id]
        person_record['activities'].append(self._activity_to_dict(activity))
        person_record['last_seen'] = max(person_record['last_seen'], timestamp)
        person_record['activity_types'].add(activity_type)
        person_record['tickets_involved'].add(ticket_id)
        
        # Update statistics
        self.people_database['statistics']['total_activities'] += 1
        self.people_database['statistics']['by_activity_type'][activity_type] = \
            self.people_database['statistics']['by_activity_type'].get(activity_type, 0) + 1

    def print_summary(self) -> None:
        """Print a summary of the people analysis."""
        print("\nPeople Activity Analysis Summary")
        print("==============================")
        print(f"Total people found: {len(self.people_database['people'])}")
        print(f"Total activities recorded: {self.people_database['statistics']['total_activities']}")
        print(f"Total tickets analyzed: {len(self.people_database['statistics']['tickets_analyzed'])}")
        
        print("\nActivity types:")
        for activity_type, count in self.people_database['statistics']['by_activity_type'].items():
            print(f"- {activity_type}: {count}")
        
        # Sort people by activity count
        sorted_people = sorted(
            [
                (person_id, len(data['activities']), person_id in self._team_members)
                for person_id, data in self.people_database['people'].items()
            ],
            key=lambda x: x[1],
            reverse=True
        )
        
        print("\nPeople Activity Counts:")
        print("----------------------")
        for person_id, activity_count, is_support in sorted_people:
            support_tag = "[Support Team]" if is_support else ""
            print(f"{person_id}: {activity_count} {support_tag}")

    def _activity_to_dict(self, activity: PersonActivity) -> Dict:
        """Convert PersonActivity object to dictionary."""
        return {
            'person_id': activity.person_id,
            'activity_type': activity.activity_type,
            'ticket_id': activity.ticket_id,
            'timestamp': activity.timestamp,
            'details': activity.details
        } 