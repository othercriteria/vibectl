# Chaos Monkey Overseer TODOs

## Agent Tagging for Terminal Display

### Background
Currently, the Overseer UI displays Blue and Red agent logs with agent-specific theming using color schemes, but there's no semantic tagging of log content. This makes it harder to automatically identify important events or highlight specific types of operations.

### Proposed Agent Tagging System
Implement a structured tagging system for both Blue (Defense) and Red (Offense) agents to provide better visualization and filtering in the Overseer UI:

1. **Tag Format**: Use a standardized tag format like `[TAG_TYPE:value]` or `[ACTION:operation]` to make parsing consistent.

2. **Blue Agent Tags**:
   - `[DEFENSE:monitor]` - When monitoring system state
   - `[DEFENSE:detect]` - When detecting anomalies
   - `[DEFENSE:mitigate]` - When taking action to mitigate attacks
   - `[DEFENSE:restore]` - When restoring services or components
   - `[DEFENSE:alert]` - When raising alerts about system state

3. **Red Agent Tags**:
   - `[ATTACK:scan]` - When scanning for vulnerabilities
   - `[ATTACK:exploit]` - When exploiting vulnerabilities
   - `[ATTACK:disrupt]` - When disrupting services
   - `[ATTACK:persist]` - When establishing persistence
   - `[ATTACK:escalate]` - When escalating privileges

4. **Severity Levels**:
   - `[SEVERITY:low]`
   - `[SEVERITY:medium]`
   - `[SEVERITY:high]`
   - `[SEVERITY:critical]`

5. **Target Tagging**:
   - `[TARGET:pod/name]`
   - `[TARGET:service/name]`
   - `[TARGET:node/name]`

### UI Enhancements for Tags
Once agent tagging is implemented, the Overseer UI should be enhanced to:

1. **Visually Highlight Tags** - Apply distinct styling to different tag types
2. **Filter by Tag** - Allow filtering log display by specific tags
3. **Tag Statistics** - Show count of different tag types for quick assessment
4. **Timeline View** - Create a timeline visualization of tagged events
5. **Correlation** - Correlate related Blue/Red agent activities with matching tags

### Implementation Plan
1. Update agent code to include standardized tags in log output
2. Modify the Terminal component to recognize and parse tags
3. Add visual styling for different tag types
4. Implement filtering capabilities based on tags
5. Create additional visualizations leveraging tag data

### Priority: Medium
This enhancement would significantly improve the usefulness of the agent logs in the Overseer UI, making it easier to understand the relationship between offensive and defensive actions in the Kubernetes cluster.
