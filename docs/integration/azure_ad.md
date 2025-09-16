# Azure AD/ADFS Integration

CHAOTICA supports integration with Azure Active Directory (Azure AD) and Active Directory Federation Services (ADFS) for single sign-on (SSO) and automated user provisioning. This guide covers setup, configuration, and troubleshooting.

## Overview

### Benefits of Azure AD Integration

**Single Sign-On (SSO)**:
- Users authenticate once with their corporate credentials
- Seamless access to CHAOTICA without separate login
- Reduced password fatigue and security risks
- Centralized access management

**Automated User Management**:
- Automatic user account creation from Azure AD
- Role and group mapping from directory services
- Synchronized profile information and attributes
- Automated deprovisioning when users leave

**Enhanced Security**:
- Centralized security policies and compliance
- Multi-factor authentication support
- Conditional access policies
- Enterprise-grade audit logging

### Supported Authentication Methods

**Azure Active Directory**:
- OAuth 2.0 / OpenID Connect
- SAML 2.0 federation
- Modern authentication protocols
- Cloud-based directory service

**Active Directory Federation Services (ADFS)**:
- On-premises federation service
- SAML 2.0 assertions
- Windows Integrated Authentication
- Hybrid cloud scenarios

## Azure AD Configuration

### Prerequisites

**Azure AD Requirements**:
- Azure AD tenant with appropriate licensing
- Global Administrator or Application Administrator role
- CHAOTICA instance with HTTPS enabled
- Domain verification completed

**CHAOTICA Requirements**:
- HTTPS configured with valid SSL certificate
- ADFS integration enabled in settings
- Appropriate environment variables configured
- Network connectivity to Azure AD endpoints

### Step 1: Register Application in Azure AD

1. **Access Azure Portal**
   - Navigate to https://portal.azure.com
   - Sign in with Global Administrator account
   - Go to Azure Active Directory

2. **Create App Registration**
   ```
   Name: CHAOTICA Security Platform
   Supported account types: Accounts in this organizational directory only
   Redirect URI: https://your-chaotica-instance.com/oauth2/callback
   ```

3. **Configure Application Settings**
   - Note the Application (client) ID
   - Note the Directory (tenant) ID
   - Create client secret and note the value
   - Configure additional redirect URIs if needed

4. **Set API Permissions**
   ```
   Microsoft Graph Permissions:
   - User.Read (Delegated) - Read user profile
   - User.ReadBasic.All (Application) - Read all users' basic profiles
   - Group.Read.All (Application) - Read all groups (optional)
   - Directory.Read.All (Application) - Read directory data (optional)
   ```

5. **Grant Admin Consent**
   - Click "Grant admin consent for [Tenant Name]"
   - Confirm the consent for all configured permissions

### Step 2: Configure CHAOTICA Settings

**Environment Variables**:
```bash
# Azure AD Configuration
ADFS_CLIENT_ID=your-application-client-id
ADFS_CLIENT_SECRET=your-client-secret-value
ADFS_TENANT_ID=your-directory-tenant-id

# Optional: Custom authority URL
ADFS_AUTHORITY=https://login.microsoftonline.com/your-tenant-id

# Enable Azure AD authentication
ADFS_ENABLED=True
ADFS_AUTO_LOGIN=False  # Set to True to redirect automatically
```

**CHAOTICA Application Settings**:
Navigate to Django admin → Constance → Config:
```
ADFS_ENABLED: True
ADFS_AUTO_LOGIN: False (or True for automatic redirect)
REGISTRATION_ENABLED: False (disable self-registration)
LOCAL_LOGIN_ENABLED: True (allow fallback to local accounts)
```

### Step 3: User and Group Mapping

**Claim Mapping Configuration**:
```python
# In settings.py (advanced configuration)
AUTH_ADFS = {
    "AUDIENCE": os.environ.get("ADFS_CLIENT_ID"),
    "CLIENT_ID": os.environ.get("ADFS_CLIENT_ID"),
    "CLIENT_SECRET": os.environ.get("ADFS_CLIENT_SECRET"),
    "CLAIM_MAPPING": {
        "first_name": "given_name",
        "last_name": "family_name",
        "email": "email",
        "username": "upn"  # User Principal Name
    },
    "GROUPS_CLAIM": "groups",
    "MIRROR_GROUPS": True,
    "USERNAME_CLAIM": "upn",
    "TENANT_ID": os.environ.get("ADFS_TENANT_ID"),
    "RELYING_PARTY_ID": os.environ.get("ADFS_CLIENT_ID")
}
```

**Group-to-Role Mapping**:
```python
# Custom group mapping (in settings.py)
ADFS_GROUP_TO_ROLE_MAPPING = {
    "CHAOTICA-Administrators": ["Global: Admin"],
    "CHAOTICA-Managers": ["Global: Delivery Manager"],
    "CHAOTICA-Consultants": ["Global: User"],
    "CHAOTICA-Sales": ["Global: Sales Manager"]
}
```

## ADFS On-Premises Configuration

### ADFS Server Setup

**Prerequisites**:
- Windows Server with ADFS role installed
- SSL certificate for ADFS service
- Active Directory domain controller access
- Network connectivity from CHAOTICA to ADFS

**ADFS Configuration Steps**:

1. **Create Relying Party Trust**
   ```
   Display Name: CHAOTICA Security Platform
   Identifier: https://your-chaotica-instance.com
   SAML 2.0 SSO URL: https://your-chaotica-instance.com/oauth2/callback
   ```

2. **Configure Claims Rules**
   ```xml
   <!-- UPN Claim Rule -->
   c:[Type == "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/upn"]
   => issue(Type = "upn", Value = c.Value);

   <!-- Email Claim Rule -->
   c:[Type == "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress"]
   => issue(Type = "email", Value = c.Value);

   <!-- Name Claims -->
   c:[Type == "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname"]
   => issue(Type = "given_name", Value = c.Value);
   
   c:[Type == "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname"]
   => issue(Type = "family_name", Value = c.Value);
   ```

3. **Group Claims Configuration**
   ```xml
   <!-- Group Membership Claims -->
   c:[Type == "http://schemas.microsoft.com/ws/2008/06/identity/claims/groupsid", 
      Value =~ "(?i)^CHAOTICA-"]
   => issue(Type = "groups", Value = c.Value);
   ```

### CHAOTICA ADFS Configuration

**Environment Variables for ADFS**:
```bash
# ADFS Server Configuration
ADFS_CLIENT_ID=https://your-chaotica-instance.com
ADFS_AUTHORITY=https://your-adfs-server.domain.com/adfs
ADFS_TENANT_ID=your-adfs-realm-or-domain

# Certificate configuration (if using certificate-based auth)
ADFS_CERTIFICATE_PATH=/path/to/certificate.crt
ADFS_PRIVATE_KEY_PATH=/path/to/private.key
```

## User Provisioning

### Automatic User Creation

**First-Time Login Process**:
1. User attempts to access CHAOTICA
2. Redirected to Azure AD/ADFS for authentication
3. User authenticates with corporate credentials
4. CHAOTICA receives authentication response with claims
5. System creates new user account with mapped attributes
6. User is logged in and redirected to dashboard

**User Attribute Mapping**:
```python
# Example user creation from claims
def create_user_from_claims(claims):
    user_data = {
        'username': claims.get('upn', ''),
        'email': claims.get('email', ''),
        'first_name': claims.get('given_name', ''),
        'last_name': claims.get('family_name', ''),
        'is_active': True
    }
    
    # Create user account
    user = User.objects.create(**user_data)
    
    # Map groups to roles
    groups = claims.get('groups', [])
    for group in groups:
        if group in ADFS_GROUP_TO_ROLE_MAPPING:
            # Assign roles based on group membership
            assign_role(user, ADFS_GROUP_TO_ROLE_MAPPING[group])
    
    return user
```

### Role and Permission Mapping

**Organizational Unit Assignment**:
```python
# Map Azure AD groups to organizational units
ADFS_GROUP_TO_UNIT_MAPPING = {
    "CHAOTICA-London-Team": "london-office",
    "CHAOTICA-NYC-Team": "new-york-office", 
    "CHAOTICA-Remote-Team": "remote-consultants"
}
```

**Dynamic Role Assignment**:
```python
# Role assignment based on claims
def assign_roles_from_claims(user, claims):
    groups = claims.get('groups', [])
    
    # Clear existing roles
    user.groups.clear()
    
    # Assign new roles based on current group membership
    for group_name in groups:
        if group_name.startswith('CHAOTICA-'):
            role = map_group_to_role(group_name)
            if role:
                user.groups.add(role)
```

## Advanced Configuration

### Conditional Access Integration

**Azure AD Conditional Access**:
- Device compliance requirements
- Location-based access policies
- Risk-based authentication
- Multi-factor authentication enforcement

**Configuration Example**:
```json
{
    "conditionalAccess": {
        "requireMFA": true,
        "allowedLocations": ["office-network", "vpn-ranges"],
        "requiredDeviceCompliance": true,
        "sessionControls": {
            "signInFrequency": "24h",
            "persistentBrowser": false
        }
    }
}
```

### Custom Claims and Attributes

**Extended User Attributes**:
```python
# Custom claim mapping for extended attributes
CUSTOM_CLAIM_MAPPING = {
    "employee_id": "extension_EmployeeID",
    "department": "department", 
    "manager": "manager",
    "job_title": "jobTitle",
    "office_location": "officeLocation",
    "phone_number": "telephoneNumber"
}
```

**Profile Enhancement**:
```python
def enhance_user_profile(user, claims):
    profile, created = UserProfile.objects.get_or_create(user=user)
    
    # Map extended attributes
    profile.employee_id = claims.get('extension_EmployeeID', '')
    profile.department = claims.get('department', '')
    profile.job_title = claims.get('jobTitle', '')
    profile.office_location = claims.get('officeLocation', '')
    profile.phone = claims.get('telephoneNumber', '')
    
    profile.save()
```

### Multi-Tenant Configuration

**Supporting Multiple Azure AD Tenants**:
```python
# Multi-tenant configuration
MULTI_TENANT_CONFIG = {
    "tenant1.onmicrosoft.com": {
        "client_id": "tenant1-client-id",
        "client_secret": "tenant1-secret",
        "authority": "https://login.microsoftonline.com/tenant1-id"
    },
    "tenant2.onmicrosoft.com": {
        "client_id": "tenant2-client-id", 
        "client_secret": "tenant2-secret",
        "authority": "https://login.microsoftonline.com/tenant2-id"
    }
}
```

## Testing and Validation

### Testing SSO Integration

**Manual Testing Checklist**:
- [ ] User can access CHAOTICA login page
- [ ] SSO redirect to Azure AD/ADFS works
- [ ] Authentication with corporate credentials succeeds
- [ ] User account is created with correct attributes
- [ ] Group memberships are mapped to appropriate roles
- [ ] User can access authorized resources
- [ ] Logout process works correctly

**Automated Testing**:
```python
import pytest
from django.test import TestCase
from django.contrib.auth.models import User

class TestAzureADIntegration(TestCase):
    def test_user_creation_from_claims(self):
        claims = {
            'upn': 'john.doe@company.com',
            'email': 'john.doe@company.com',
            'given_name': 'John',
            'family_name': 'Doe',
            'groups': ['CHAOTICA-Consultants']
        }
        
        user = create_user_from_claims(claims)
        
        assert user.username == 'john.doe@company.com'
        assert user.email == 'john.doe@company.com'
        assert user.first_name == 'John'
        assert user.groups.filter(name='Global: User').exists()
```

### Troubleshooting Authentication

**Common Issues and Solutions**:

1. **Redirect URI Mismatch**
   ```
   Error: AADSTS50011 - Redirect URI mismatch
   Solution: Verify redirect URI in Azure AD matches CHAOTICA configuration
   ```

2. **Insufficient Permissions**
   ```
   Error: AADSTS65001 - Consent required
   Solution: Grant admin consent for required permissions in Azure AD
   ```

3. **Token Validation Errors**
   ```
   Error: Invalid signature or token expired
   Solution: Check system clocks, certificate configuration, and token lifetime
   ```

4. **User Creation Failures**
   ```
   Error: User account creation failed
   Solution: Verify claim mapping and required user attributes
   ```

### Diagnostic Tools

**Logging Configuration**:
```python
# Enhanced logging for ADFS integration
LOGGING = {
    'version': 1,
    'handlers': {
        'adfs_file': {
            'class': 'logging.FileHandler',
            'filename': '/var/log/chaotica/adfs.log',
            'level': 'DEBUG',
        }
    },
    'loggers': {
        'django_auth_adfs': {
            'handlers': ['adfs_file'],
            'level': 'DEBUG',
            'propagate': False,
        }
    }
}
```

**Token Inspection**:
```python
# Debug token contents
import jwt
import json

def inspect_token(token):
    # Decode without verification for debugging
    decoded = jwt.decode(token, options={"verify_signature": False})
    print(json.dumps(decoded, indent=2))
```

## Security Considerations

### Security Best Practices

**Certificate Management**:
- Use proper SSL certificates for all endpoints
- Regularly rotate client secrets and certificates
- Store secrets securely using environment variables or key vaults
- Monitor certificate expiration dates

**Network Security**:
- Use HTTPS for all authentication flows
- Implement proper firewall rules
- Consider network isolation for ADFS servers
- Monitor authentication traffic and logs

**Access Controls**:
- Implement principle of least privilege
- Regularly review group memberships and role assignments
- Use conditional access policies where possible
- Monitor for unusual authentication patterns

### Compliance and Audit

**Audit Logging**:
```python
# Log all authentication events
import logging

auth_logger = logging.getLogger('auth.adfs')

def log_authentication_event(event_type, user, details):
    auth_logger.info(f"ADFS Auth: {event_type}", extra={
        'user': user.username if user else 'anonymous',
        'event_type': event_type,
        'details': details,
        'ip_address': get_client_ip(),
        'user_agent': get_user_agent()
    })
```

**Compliance Reporting**:
- Regular access reviews and attestations
- Authentication success/failure reporting
- User provisioning and deprovisioning audits
- Role and permission change tracking

## Maintenance and Operations

### Regular Maintenance Tasks

**Monthly Tasks**:
- Review and rotate client secrets (as needed)
- Check certificate expiration dates
- Review user access and role assignments
- Monitor authentication success rates

**Quarterly Tasks**:
- Full integration testing
- Security assessment of configuration
- Review group-to-role mappings
- Update documentation and procedures

### Monitoring and Alerting

**Key Metrics to Monitor**:
- Authentication success/failure rates
- User provisioning failures
- Token validation errors
- Certificate expiration warnings
- Unusual access patterns

**Alerting Configuration**:
```python
# Example alert configuration
AUTHENTICATION_ALERTS = {
    'high_failure_rate': {
        'threshold': 0.1,  # 10% failure rate
        'window': '15m',
        'recipients': ['security@company.com']
    },
    'certificate_expiry': {
        'threshold': '30d',  # 30 days before expiry
        'recipients': ['it-ops@company.com']
    }
}
```

## Related Topics

- [User Management](../user_guide/team/user_management.md) - User account and permission management
- [Security](../security/access_control.md) - Security policies and access control
- [Administration](../administration/system_management.md) - System configuration and maintenance
- [API Documentation](../development/api_documentation.md) - API authentication methods