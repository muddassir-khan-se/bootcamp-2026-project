# Customer Support SLA Escalation Engine

**Bootcamp 2026 Project** by Muddassir Khan

## Project Overview

The Customer Support SLA Escalation Engine is a ticket management system designed to handle Service Level Agreement (SLA) timers for support tickets. The system tracks ticket creation, assignment, and escalation based on SLA rules, with special handling for process crashes and restarts.

## Key Features

- **Ticket Lifecycle Management**: Create, claim, and track support tickets
- **In-Memory SLA Timers**: Real-time SLA tracking with automatic escalation
- **Crash Recovery**: Graceful handling of process restarts with timer persistence
- **Escalation Workflow**: Automatic escalation when SLA thresholds are breached
- **Unit Testing**: Comprehensive test coverage for all core components
- **CI/CD Pipeline**: GitHub Actions for automated testing and validation

## Problem Statement

Support tickets must be claimed by an agent within a guaranteed 1-hour SLA window. The system uses in-memory timers to track SLA deadlines. A critical challenge is ensuring ticket escalation continues even after process crashes or restarts, when the in-memory state is lost.

## Project Goals

1. Provide a clear API for ticket lifecycle operations (create, claim, check status)
2. Enforce independent SLA monitoring with automatic escalation
3. Record ticket state transitions with accurate timestamps
4. Handle the failure mode where SLA timers disappear after restart
5. Demonstrate resilience through comprehensive testing

## Repository Structure

```
.
├── src/                          # Source code
│   ├── ticket.ts                 # Ticket model and interfaces
│   ├── sla-manager.ts            # SLA timer management
│   ├── ticket-service.ts         # Core ticket operations
│   └── escalation-engine.ts      # Escalation logic
├── tests/                        # Unit and integration tests
│   ├── ticket.test.ts
│   ├── sla-manager.test.ts
│   ├── ticket-service.test.ts
│   └── escalation-engine.test.ts
├── screenshots/                  # Visual artifacts and demos
├── .github/workflows/            # CI/CD configuration
│   └── ci.yml                    # GitHub Actions workflow
├── README.md                     # This file
├── requirements.txt              # Project dependencies
└── .gitignore                    # Git ignore rules
```

## Getting Started

### Prerequisites

- Node.js 20.x or later
- npm or yarn
- Git

### Installation

```bash
git clone https://github.com/muddassir-khan-se/bootcamp-2026-project.git
cd bootcamp-2026-project
npm install
```

### Running Tests

```bash
npm test
```

### Building

```bash
npm run build
```

## Core Components

### Ticket Model
- **ID**: Unique identifier for each ticket
- **Status**: open → claimed → escalated → resolved
- **Priority**: low, medium, high
- **SLA Deadline**: Calculated from creation time + SLA window
- **Timestamps**: Created, claimed, escalated, resolved

### SLA Manager
- Tracks in-memory timers for each active ticket
- Monitors SLA threshold breaches
- Triggers escalation when SLA is exceeded
- Handles timer restoration on system restart

### Escalation Engine
- Evaluates escalation conditions
- Updates ticket status and priority
- Records escalation events with timestamps
- Prevents duplicate escalation

### Ticket Service
- Public API for ticket operations
- Enforces business rules
- Coordinates between components
- Maintains ticket registry

## API Reference

```typescript
// Create a new support ticket
createTicket(subject: string, priority: 'low' | 'medium' | 'high'): Ticket

// Claim a ticket for an agent
claimTicket(ticketId: string, agentId: string): void

// Retrieve ticket details
getTicket(ticketId: string): Ticket | null

// List all active tickets
listActiveTickets(): Ticket[]

// Check current SLA status
checkSLAStatus(ticketId: string): SLAStatus

// Resolve a ticket
resolveTicket(ticketId: string): void
```

## Testing Strategy

The project includes comprehensive unit tests covering:
- ✅ Ticket creation and lifecycle transitions
- ✅ SLA timer accuracy and escalation triggers
- ✅ Edge cases (duplicate claims, expired deadlines)
- ✅ Error handling and validation
- ✅ Timestamp recording and audit trails

Run tests with:
```bash
npm test
```

Generate coverage report:
```bash
npm run test:coverage
```

## Development Workflow

1. **Create Feature Branch**:
   ```bash
   git checkout -b muddassir-khan/use-case-name
   ```

2. **Implement Changes**: Add code to `src/` directory

3. **Write Tests**: Add tests to `tests/` directory

4. **Run Tests Locally**:
   ```bash
   npm test
   ```

5. **Commit Changes**:
   ```bash
   git add .
   git commit -m "[Bootcamp 2026] Use Case: Brief description"
   ```

6. **Push and Create PR**:
   ```bash
   git push -u origin muddassir-khan/use-case-name
   ```

7. **Create Pull Request** with title:
   ```
   [Bootcamp 2026] Muddassir Khan — Customer Support SLA Escalation Engine
   ```

## Continuous Integration

GitHub Actions CI runs automatically on every push and pull request:
- Runs complete test suite
- Validates code style
- Checks build process
- Generates coverage metrics

See `.github/workflows/ci.yml` for details.

## Known Limitations & Failure Modes

1. **In-Memory State Loss**: SLA timers are stored in-memory; process crashes will lose this state
2. **Single Process**: Current implementation assumes single-process execution
3. **Persistence**: No persistence layer; consider database integration for production

## Future Enhancements

- [ ] Database persistence for SLA state
- [ ] Distributed system support (multiple processes/servers)
- [ ] Advanced escalation rules engine
- [ ] REST API interface
- [ ] Real-time notifications
- [ ] Analytics and reporting dashboard

## Contributing

When contributing to this project:
1. Follow the development workflow above
2. Ensure all tests pass locally
3. Add new tests for new features
4. Update documentation as needed
5. Request code review before merging

## References

- [Bootcamp 2026 Guidelines](https://bootcamp2026.example.com)
- [SLA Best Practices](https://example.com/sla-guide)
- [TypeScript Documentation](https://www.typescriptlang.org/docs/)

---

**Project Status**: Active Development  
**Last Updated**: June 22, 2026  
**Author**: Muddassir Khan  
**License**: Bootcamp 2026 Program
