---
name: agentic-rag
description: Implements Agentic RAG using Vercel AI SDK principles (Reasoning Loop, Dynamic Retrieval).
---

# Agentic RAG (Retrieval-Augmented Generation)

This skill implements an "Agentic" approach to RAG, where retrieval is treated as a *tool* that the Agent actively decides to use, rather than a passive pre-processing step. This enables multi-step reasoning and dynamic information gathering.

## Core Principles (Vercel AI SDK Design)

1.  **Tool-Based Retrieval**: Retrieval is a function (Tool) available to the LLM.
2.  **Reasoning Loop**: The Agent enters a loop: `Thought -> Action (Search/Retrieve) -> Observation -> Thought`.
3.  **Dynamic Querying**: The Agent formulates search queries based on the *current state* of its reasoning, not just the initial user prompt.

## Workflow

### 1. Assessment
- **Trigger**: User asks a question requiring external knowledge or specific codebase details not in current context.
- **Decision**: "Do I have enough information? No -> Call Retrieval Tool."

### 2. The Reasoning Loop (ToolLoop)

The Agent operates in a loop (conceptually similar to `ToolLoopAgent` in Vercel AI SDK):

**Step 1: Formulate Hypothesis/Question**
- "To answer X, I first need to know Y."
- *Action*: Call `search_codebase` or `web_search` with query for Y.

**Step 2: Observe & Refine**
- "I found information about Y. Now I see that Y depends on Z."
- *Action*: Call `search_codebase` for Z.

**Step 3: Synthesis**
- "I have Y and Z. I can now synthesize the answer to X."

### 3. Tool Definition (Conceptual)

The Agent should utilize tools like `search_codebase` with this mindset:

```typescript
// Concept from Vercel AI SDK
const retrievalTool = tool({
  description: 'Search the codebase for context',
  parameters: z.object({ query: z.string() }),
  execute: async ({ query }) => {
    // Perform vector search or keyword search
    return results;
  },
});
```

## Best Practices for the Agent
- **Iterative Search**: Don't just search once. If the first result is insufficient, refine the query and search again.
- **Source Verification**: Always check the file path and content returned by the tool.
- **Reasoning Traces**: explicitly state *why* you are searching for something. "I am searching for `auth_middleware` to understand how the user is validated."

## Example Scenario

**User**: "Why is the payment flow failing?"

**Agent (Agentic RAG Mode)**:
1.  *Thought*: "I need to find the payment processing code."
2.  *Action*: `search_codebase("payment processing flow")`
3.  *Observation*: "Found `process_payment` function in `services/payment.ts`. It calls `validate_user`."
4.  *Thought*: "Maybe `validate_user` is failing. I need to check its definition."
5.  *Action*: `read_file("services/user.ts")`
6.  *Conclusion*: "The failure is likely in the validation logic..."

## Integration
This pattern is natively supported by the `ToolLoopAgent` abstraction in Vercel AI SDK 6+. Use this mental model when executing tasks.
