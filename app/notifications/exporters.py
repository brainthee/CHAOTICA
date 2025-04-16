import json
import logging
from django.core.serializers.json import DjangoJSONEncoder
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from jobtracker.models import OrganisationalUnitRole
from .models import SubscriptionRule, BaseRuleCriteria, DynamicRuleCriteria, GlobalRoleCriteria, OrgUnitRoleCriteria, JobRoleCriteria, PhaseRoleCriteria, PhaseRoleCriteria

logger = logging.getLogger(__name__)

class RuleExporter:
    """
    Exports subscription rules to a JSON format
    """
    
    def export_rule(self, rule):
        """
        Export a single rule to a dictionary
        """
        rule_data = {
            'name': rule.name,
            'description': rule.description,
            'notification_type': rule.notification_type,
            'is_active': rule.is_active,
            'criteria': []
        }

        # Export all criteria - we need to gather them from each related_name
        criteria = []
        criteria.extend(list(rule.globalrolecriteria_criteria.all()))
        criteria.extend(list(rule.orgunitrolecriteria_criteria.all()))
        criteria.extend(list(rule.jobrolecriteria_criteria.all()))
        criteria.extend(list(rule.phaserolecriteria_criteria.all()))
        criteria.extend(list(rule.dynamicrulecriteria_criteria.all()))
        
        for criterion in criteria:
            criterion_data = self._export_criterion(criterion)
            if criterion_data:
                rule_data['criteria'].append(criterion_data)
        
        return rule_data
    
    def _export_criterion(self, criterion):
        """
        Export a single criterion to a dictionary
        """
        # Get the concrete class instance
        concrete_class = criterion.get_concrete_class()
        if not concrete_class:
            return None
        
        # Base data
        criterion_data = {
            'criteria_type': concrete_class.__class__.__name__,
        }
        
        # Add type-specific data
        if isinstance(concrete_class, GlobalRoleCriteria):
            criterion_data['role'] = concrete_class.role
        elif isinstance(concrete_class, OrgUnitRoleCriteria):
            criterion_data['unit_role'] = concrete_class.unit_role.id
        elif isinstance(concrete_class, JobRoleCriteria):
            criterion_data['role_id'] = concrete_class.role_id
        elif isinstance(concrete_class, PhaseRoleCriteria):
            criterion_data['role_id'] = concrete_class.role_id
        elif isinstance(concrete_class, DynamicRuleCriteria):
            criterion_data['criteria_name'] = concrete_class.criteria_name
            criterion_data['parameters'] = concrete_class.parameters
        
        return criterion_data
    
    def export_rules(self, rules):
        """
        Export a queryset of rules to a JSON-serializable list of dictionaries
        """
        result = []
        for rule in rules:
            result.append(self.export_rule(rule))
        return result
    
    def export_rules_to_json(self, rules):
        """
        Export rules to a JSON string
        """
        data = self.export_rules(rules)
        return json.dumps(data, cls=DjangoJSONEncoder, indent=2)


class RuleImporter:
    """
    Imports subscription rules from a JSON format
    """
    
    def __init__(self):
        self.errors = []
    
    def import_from_json(self, json_data):
        """
        Import rules from a JSON string
        """
        try:
            data = json.loads(json_data)
            return self.import_rules(data)
        except json.JSONDecodeError as e:
            self.errors.append(f"Invalid JSON: {str(e)}")
            return []
    
    @transaction.atomic
    def import_rules(self, rules_data):
        """
        Import a list of rule dictionaries
        Returns a list of created rule objects
        """
        imported_rules = []
        
        for rule_data in rules_data:
            try:
                rule = self._import_rule(rule_data)
                if rule:
                    imported_rules.append(rule)
            except Exception as e:
                self.errors.append(f"Error importing rule '{rule_data.get('name', 'unknown')}': {str(e)}")
                logger.exception(f"Error importing rule: {e}")
        
        return imported_rules
    
    def _import_rule(self, rule_data):
        """
        Import a single rule from a dictionary
        """
        # Create the rule
        rule = SubscriptionRule.objects.create(
            name=rule_data.get('name'),
            description=rule_data.get('description', ''),
            notification_type=rule_data.get('notification_type'),
            is_active=rule_data.get('is_active', True),
        )
        
        # Import criteria
        criteria_data = rule_data.get('criteria', [])
        for criterion_data in criteria_data:
            try:
                self._import_criterion(rule, criterion_data)
            except Exception as e:
                logger.exception(f"Error importing criterion for rule {rule.name}: {e}")
                self.errors.append(f"Error importing criterion for rule '{rule.name}': {str(e)}")
        
        return rule
    
    def _import_criterion(self, rule, criterion_data):
        """
        Import a single criterion for a rule
        """
        criteria_type = criterion_data.get('criteria_type')
        
        # Create the appropriate criterion type
        if criteria_type == 'GlobalRoleCriteria':
            role = criterion_data.get('role')
            
            criterion = GlobalRoleCriteria.objects.create(
                rule=rule,
                role=role,
            )
            
        elif criteria_type == 'OrgUnitRoleCriteria':
            unit_role = criterion_data.get('unit_role')
            
            criterion = OrgUnitRoleCriteria.objects.create(
                rule=rule,
                unit_role=OrganisationalUnitRole.objects.get(id=unit_role),
            )
            
        elif criteria_type == 'JobRoleCriteria':
            role_id = criterion_data.get('role_id')
            
            criterion = JobRoleCriteria.objects.create(
                rule=rule,
                role_id=role_id,
            )
            
        elif criteria_type == 'PhaseRoleCriteria':
            role_id = criterion_data.get('role_id')
            
            criterion = PhaseRoleCriteria.objects.create(
                rule=rule,
                role_id=role_id,
            )
            
        elif criteria_type == 'DynamicRuleCriteria':
            criteria_name = criterion_data.get('criteria_name')
            parameters = criterion_data.get('parameters')
            if not criteria_name:
                raise ValueError("DynamicRuleCriteria requires criteria_name")
            
            criterion = DynamicRuleCriteria.objects.create(
                rule=rule,
                criteria_name=criteria_name,
                parameters=parameters,
            )
            
        else:
            raise ValueError(f"Unknown criteria type: {criteria_type}")
        
        return criterion