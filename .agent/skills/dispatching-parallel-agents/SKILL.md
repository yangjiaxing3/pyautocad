---
name: dispatching-parallel-agents
description: Implements the "Manager-Worker" pattern for parallel task execution.
---

# Dispatching Parallel Agents (Manager-Worker Pattern)

This skill enables the Agent to act as a "Manager" that decomposes complex tasks into independent sub-tasks, dispatches them to "Worker Agents" (simulated or real sub-agents) for parallel execution, and aggregates the results.

## When to Use
- **Complex Tasks**: When a user request involves multiple distinct components (e.g., "Fix the backend API error AND update the frontend UI").
- **Independent Operations**: When sub-tasks do not strictly depend on each other's sequential output.
- **Efficiency**: To speed up execution by "parallelizing" work (conceptually or via actual tool calls).

## Workflow

### 1. Analysis & Decomposition (The Manager)
- **Input**: User request.
- **Action**: Analyze the request to identify independent sub-tasks.
- **Output**: A list of `Task` objects.

```typescript
interface Task {
  id: string;
  description: string;
  context: string; // Necessary file paths, code snippets, or requirements
  type: "frontend" | "backend" | "testing" | "other";
}
```

### 2. Dispatching (The Workers)
- **Action**: For each task in the list, initiate a "Worker" execution.
- **Method**:
  - **Sub-Agent Tool**: Use `subagent-driven-development` skill if available to spawn a sub-agent.
  - **Sequential Emulation**: If true parallelism isn't available, execute sequentially but maintain *independent context* for each task to avoid pollution.
- **Instruction to Worker**: "You are a specialized worker for [type]. Your task is [description]. Focus ONLY on this task."

### 3. Aggregation & Review
- **Action**: Collect outputs from all workers.
- **Verification**: Check if all sub-tasks are completed successfully.
- **Merge**: Combine code changes or reports into a final response.

## Example Prompt for Manager Agent

```markdown
You are the Manager Agent. The user wants to: "Refactor the login API to return JWT and update the React login form to store it."

**Plan:**
1.  **Backend Task**: Modify `api/auth.py` to issue JWTs.
2.  **Frontend Task**: Modify `components/LoginForm.tsx` to handle JWT storage.

**Execution:**
- Dispatch Backend Task -> [Worker A]
- Dispatch Frontend Task -> [Worker B]

**Aggregation:**
- Verify both tasks passed tests.
- Present final summary to user.
```

## Rules
- **Isolation**: Workers should not modify the same file simultaneously unless carefully coordinated.
- **Error Handling**: If a worker fails, the Manager must decide to retry or report the failure.
- **Clear Context**: Provide workers with *only* the necessary context to reduce noise.
