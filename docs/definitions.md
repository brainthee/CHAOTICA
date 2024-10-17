# Definitions

While you can make CHAOTICA work how you like regardless of phrasing; for consistency it's a good idea to establish some common understanding. 

## Core

### Job

A job is a discrete piece of work for a client. Typically tied to a package of work or system.

!!! Example
    The client want's their e-commerce system testing. 6 months later they come back and want their internal office network testing. These would be two separate discrete pieces of work and therefore two separate jobs.

### Phase

A phase is a child of a Job and is generally tied one to one to a service.

!!! Example
    Using the above `e-commerce` job as an example; if the client wanted their website tested as well as the underlying network the servers are on, there would be two phases:
    
    1. `e-Commerce Portal` with the `Web Application Assessment` service
    2. `e-Commerce Infrastructure` with the `Infrastructure Assessment` service

### Client

Someone you're doing work for!

### Framework Agreement

This is a concept where you can tie multiple jobs together via the client for purposes of collation or reporting.

!!! Example
    Rather than a client contract you for a specific project; if they instead buy x days as an annual contract in one go. This contract can be entered in CHAOTICA as a Framework Agreement and can be used to keep track of days "spent" against that contract.

## Operations

### Project

A project is a lightweight version of a Job that typically doesn't have a client associated. Normally this might be some internal project or reference. 

!!! Example
    I have a project I would like to schedule on several people that isn't client-facing but aims to complete some internal task such as building out service documentation/checklists/methodologies. 

### Service

A service is a type of offering. Generally they would have distinct methodologies or skill sets. Ultimately though - it's a service you provide.

!!! Example
    A `Web Application Assessment` has a uniquely different methodology and skill set to an `Infrastructure Assessment` so the two are likely to be different services.

### Skill

Something that makes you special :)

### Qualification

Something special you got!

### Organisational Unit

This can be considered a team. It could be a region, capability group or something similar. Most permissions are applied at the organisation unit level so you can implement as much or little compartmentalisation as suitable. Jobs are assigned to a unit. People across different units can be scheduled on jobs from other units!

!!! Example
    A company has a team of consultants across different countries. Each team largely manage their own workload or "schedule" and has their own back-office staff. Therefore it would make sense for each country to have it's own unit.