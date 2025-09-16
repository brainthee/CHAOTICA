# Adding a Client

Clients are the organizations you perform security assessments and consulting work for. This guide covers creating and managing client records in CHAOTICA.

## Prerequisites

Before adding a client, ensure you have:
- "Add Client" permissions in your role
- Basic client information gathered
- Contact details for key stakeholders

## Creating a New Client

### Step 1: Navigate to Client Management

1. Go to the main dashboard
2. Click "Clients" in the navigation menu
3. Click "Add New Client" button

### Step 2: Basic Information

Fill in the essential client details:

```
Client Name: Full legal name of the organization
Short Name: Abbreviated name or acronym (optional)
Client Type: Organization, Individual, Government, etc.
Industry: Primary industry sector
Website: Company website URL
```

**Client Name Guidelines**:
- Use the full legal entity name
- Ensure consistency in naming convention
- Avoid abbreviations in the main name field
- Use the short name field for common abbreviations

### Step 3: Address Information

Enter the primary business address:

```
Street Address: Physical address
City: City name
State/Province: State or province
Postal Code: ZIP or postal code
Country: Select from dropdown
```

**Multiple Locations**: If the client has multiple locations, add the primary headquarters first. Additional locations can be added after client creation.

### Step 4: Contact Information

Add primary contact details:

```
Phone: Main business phone number
Email: Primary contact email
Fax: Fax number (if applicable)
```

### Step 5: Classification and Security

Set appropriate security and classification levels:

```
Security Classification: Client's security clearance level
Risk Classification: Risk assessment level
Restricted Access: Enable if access should be limited
```

**Security Guidelines**:
- Set classification based on client's cleared level
- Consider the sensitivity of work to be performed
- Restrict access for highly sensitive clients

### Step 6: Financial Information

Configure billing and financial settings:

```
Currency: Primary currency for billing
Payment Terms: Standard payment terms (30 days, etc.)
Billing Contact: Separate billing contact if different
Tax ID: Client's tax identification number
```

### Step 7: Account Management

Assign account management responsibilities:

```
Primary Account Manager: Main client relationship owner
Secondary Account Manager: Backup/support manager
Client Success Manager: Post-delivery relationship manager
```

**Assignment Guidelines**:
- Assign based on client relationship and expertise
- Ensure account managers have appropriate permissions
- Consider workload distribution across the team

## Client Information Sections

### Overview Tab

**Basic Details**:
- Client name and identifiers
- Industry and classification
- Contact information
- Account manager assignments

**Status Indicators**:
- Active/Inactive status
- Last engagement date
- Upcoming scheduled work
- Outstanding issues or actions

### Contacts Tab

Manage client contacts and stakeholders:

**Adding Contacts**:
1. Click "Add Contact" in the contacts tab
2. Enter contact details (name, role, email, phone)
3. Set contact type (Technical, Business, Procurement, etc.)
4. Assign to specific areas of responsibility

**Contact Types**:
- **Primary Contact**: Main point of contact
- **Technical Contact**: Technical discussions and coordination  
- **Business Contact**: Business and commercial discussions
- **Procurement Contact**: Contract and purchasing matters
- **Security Contact**: Security clearance and compliance
- **Billing Contact**: Invoicing and payment matters

### Framework Agreements Tab

Set up overarching contractual arrangements:

**Creating Framework Agreements**:
1. Click "Add Framework Agreement"
2. Enter agreement details:
   ```
   Agreement Name: Descriptive name
   Start Date: When agreement becomes active
   End Date: Agreement expiration
   Total Value: Overall contract value
   Remaining Value: Unused contract value
   Currency: Agreement currency
   ```

**Framework Benefits**:
- Streamlined job creation under existing agreements
- Budget tracking across multiple engagements
- Simplified procurement for repeat work
- Better financial reporting and forecasting

### Documents Tab

Store client-related documentation:

**Document Types**:
- Contracts and agreements
- Statements of work
- Security clearance documentation
- Compliance certificates
- Previous reports and deliverables

**Document Management**:
- Upload files directly or link to external storage
- Set access permissions for sensitive documents
- Track document versions and updates
- Add metadata and tags for organization

### Jobs Tab

View all jobs associated with the client:

**Job Overview**:
- Historical and active engagements
- Job status and progress
- Assigned teams and resources
- Financial summary

**Quick Actions**:
- Create new job for this client
- View detailed job information
- Access job reports and deliverables
- Review job history and outcomes

### Notes Tab

Internal notes and communications:

**Note Categories**:
- General client information
- Relationship management notes
- Technical requirements and constraints
- Business development opportunities
- Issues and resolutions

**Best Practices**:
- Use @ mentions to notify team members
- Tag notes with relevant categories
- Include timestamps for important events
- Reference external systems and tickets

## Framework Agreements

Framework agreements enable efficient management of ongoing client relationships with pre-negotiated terms.

### When to Use Framework Agreements

- **Recurring Engagements**: Regular security assessments
- **Multi-Year Contracts**: Annual security programs
- **Volume Discounts**: Bulk purchasing arrangements  
- **Preferred Vendor Status**: Established partnership relationships

### Setting Up Framework Agreements

1. **Agreement Structure**:
   ```
   Name: [Client] - [Year] Security Services Framework
   Duration: Typically 1-3 years
   Value: Total contracted amount
   Terms: Payment terms and conditions
   ```

2. **Service Scope**:
   - Define included service types
   - Specify any excluded services
   - Set rate cards for different service levels
   - Include any volume discounts or incentives

3. **Resource Allocation**:
   - Reserve team capacity for framework work
   - Define response time commitments  
   - Set escalation procedures for urgent requests
   - Plan for peak demand periods

### Managing Framework Agreements

**Tracking Utilization**:
- Monitor spend against total framework value
- Track service usage by type and frequency
- Generate utilization reports for client reviews
- Alert when approaching spending thresholds

**Renewal Process**:
- Set up alerts for upcoming expirations
- Review performance and outcomes
- Gather client feedback and requirements
- Negotiate renewal terms and adjustments

## Client Classification System

### Security Classifications

Match client security requirements:

- **Public**: No special security requirements
- **Internal**: Standard business confidentiality
- **Confidential**: Enhanced protection required
- **Secret**: Government or high-security clients
- **Top Secret**: Highest security classifications

### Risk Classifications  

Assess client-related risks:

- **Low Risk**: Established relationship, standard services
- **Medium Risk**: New client or complex requirements  
- **High Risk**: Challenging requirements or relationship
- **Critical Risk**: Significant business or security risks

## Best Practices

### Client Data Management

**Data Quality**:
- Keep contact information current
- Regular review and updates
- Standardize naming conventions
- Maintain consistent formatting

**Privacy and Security**:
- Limit access to appropriate personnel
- Follow data protection regulations
- Secure handling of sensitive information
- Regular access reviews and updates

### Relationship Management

**Regular Communication**:
- Schedule periodic check-ins
- Proactive issue identification
- Business development discussions
- Feedback collection and analysis

**Service Excellence**:
- Meet or exceed service commitments
- Proactive communication about changes
- Quality delivery and follow-up
- Continuous improvement initiatives

## Integration with Jobs

### Streamlined Job Creation

When creating jobs for existing clients:
1. Client information auto-populates
2. Framework agreements are available for selection
3. Previous job templates can be reused
4. Contact information is readily available

### Consistency and Efficiency

- Standardized client information across all jobs
- Consistent billing and payment terms
- Reusable framework agreements and terms
- Historical context for better service delivery

## Troubleshooting

### Common Issues

**Duplicate Clients**:
- Search thoroughly before creating new clients
- Check variations in naming (Inc., Ltd., LLC, etc.)
- Merge duplicates if found after creation
- Implement naming standards to prevent duplicates

**Missing Framework Agreements**:
- Verify agreement has been properly created
- Check start/end dates for validity
- Ensure user has access to view agreements
- Review client assignment and permissions

**Contact Information Issues**:
- Regularly validate email addresses
- Confirm phone numbers are current
- Update contacts when personnel changes occur
- Maintain backup contacts for key roles

### Data Migration

When migrating from other systems:
- Map existing client data to CHAOTICA fields
- Validate data integrity and completeness
- Test import procedures with sample data
- Plan for data cleanup and standardization

## Related Topics

- [Managing Contacts](managing_contacts.md) - Detailed contact management
- [Jobs Management](../Jobs/managing_jobs.md) - Creating jobs for clients
- [Reporting](../reporting/overview.md) - Client reporting and analytics
- [Framework Agreements](framework_agreements.md) - Advanced agreement management