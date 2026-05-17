The capstone project topic is following: 
**Personal Knowledge Assistant**
Multi-agent system combining document RAG with web search fallback via MCP. **Research Agent** indexes personal documents, **Web Agent** handles live queries, **Synthesis Agent** combines results and provides coherent responses to user questions.

It must meet the following general requirements:

- Multi-agent architecture: at least 3 agents with clearly defined, distinct roles and responsibilities 
- RAG pipeline: meaningful retrieval-augmented generation over a domain-specific knowledge base or document corpus 
- MCP integration: at least one external data source or tool connected via MCP protocol 
- Real-world applicability: the system must solve a tangible, clearly articulated problem 
- Inter-agent communication: agents must collaborate, delegate tasks, or share context — not operate in complete isolation 
- Testability: the use case must support both positive and negative test scenarios, including edge cases and adversarial inputs 
- Demonstrability: the system must be presentable in a 2–5 minute video demo showing end-to-end functionality


---

### Non-Functional Requirements

#### Observability & Monitoring
- **LLM Tracing**: Track all agent interactions, token usage, and response quality
- **Performance Metrics**: Monitor response times, success rates, and system throughput
- **Error Tracking**: Comprehensive logging of failures and system errors
- **User Feedback**: Implement rating systems for response quality assessment
- **Resource Usage**: Track memory, CPU, and API quota consumption

#### Security & Safety
- **Input Validation**: Sanitize all user inputs and API responses
- **Content Filtering**: Implement guardrails against harmful or inappropriate content
- **Privacy Protection**: PII detection and data anonymization capabilities
- **Access Control**: Implement authentication and authorization mechanisms
- **Rate Limiting**: Prevent abuse and manage resource consumption

#### RAG Quality Assurance
- **Retrieval Accuracy**: Measure precision and recall of document retrieval
- **Answer Relevance**: Evaluate semantic similarity and factual correctness
- **Source Attribution**: Ensure proper citation and traceability
- **Hallucination Detection**: Identify and flag potentially false information
- **Bias Assessment**: Monitor for unfair or discriminatory outputs

#### Cost & Resource Management
- **Local-First Architecture**: Minimize cloud dependencies and external costs
- **Free Tier Optimization**: Stay within API limits and free service quotas
- **Efficient Processing**: Implement caching and optimize resource usage
- **Scalability**: Support concurrent users without performance degradation
- **Data Management**: Implement retention policies and storage optimization

#### Compliance & Ethics
- **Industry Standards**: Implement domain-specific compliance requirements
- **Transparency**: Provide clear information about system capabilities and limitations
- **Consent Management**: Handle user data with appropriate permissions
- **Audit Trail**: Maintain logs for accountability and debugging
- **Graceful Degradation**: Handle service failures with appropriate fallbacks


---

### Success Criteria

#### Base Requirements (70% — Pass Threshold)
1. **Working Application**: Functional multi-agent system demonstrated in video
2. **Code Delivery**: Complete codebase with clear structure and comments
3. **LLM Behavior Tests**: Both positive and negative test scenarios
   - Normal user flow validation
   - Edge case and adversarial prompt handling

#### Excellence Bonuses (30% Total)
- **+10% UX & Presentation**: Polished UI, smooth UX, investor-ready demo quality
- **+10% Data Quality**: Well-prepared datasets, proper data handling, quality validation
- **+10% Code Excellence**: Clean architecture, software engineering best practices, thoughtful design patterns (AI-generated code is fine, but show you understand it)

#### Deliverables
- **Architecture Blueprint**: Complete system design with technology stack and rationale
- **Video Demo**: 2–5 minutes with voiceover explaining functionality and code choices
- **Code Repository**: Well-structured project with README and setup instructions
- **Test Suite**: Automated tests demonstrating LLM behavior validation
- **Self-Review**: Code commentary addressing architecture decisions and trade-offs
- **Executive Summary**: A concise 1–2 page overview of the project's objectives, key findings, and business value

---

### Step-by-Step Implementation Guide

#### Phase 1: Planning & Setup (2–3 hours)
1. Choose use case and define core problem
2. **Use GenAI with internet access** (Perplexity, ChatGPT with browsing, or similar) to:
   - Research current best practices and technology trends
   - Compare agent frameworks and select optimal one
   - Identify suitable LLM providers and data sources
   - Design system architecture with latest patterns
3. **Create architecture blueprint** documenting:
   - System components and agent roles
   - Technology stack (frameworks, models, databases)
   - Data flow and integration points
   - MCP tool selections and rationale
4. Set up project structure with observability tools

#### Phase 2: Core Agent Development (10–15 hours)
1. Implement first agent with basic RAG pipeline
2. Add MCP integrations for external data
3. Build inter-agent communication layer
4. Test individual agent behaviors

#### Phase 3: Multi-Agent Orchestration (8–10 hours)
1. Connect agents with task delegation logic
2. Implement state management and error handling
3. Add monitoring and tracing
4. Iterative testing and refinement

#### Phase 4: Testing & Validation (5–8 hours)
1. Write positive test scenarios (expected behavior)
2. Write negative test scenarios (edge cases, adversarial)
3. Implement automated test suite
4. Manual testing and bug fixes

#### Phase 5: Polish & Documentation (5–7 hours)
1. Refine UI/UX if applicable
2. Clean up code and add comments
3. Write README with setup instructions (do not commit credentials!)
4. Prepare demo script and talking points

#### Phase 6: Executive Summary (1–2 hours)
1. Write a concise 1–2 page overview covering:
   - Problem statement and project objectives (why this project exists)
   - Key technical decisions and architecture highlights
   - **Results, findings, and business value**
   - Lessons learned and potential next steps
2. **Target audience:** People not involved in the details — review committee, management, investors
   > The reader should go through this section only and walk away with a full understanding of what matters most — without reading the rest of the document

#### Tips for Success
- **Short iterations**: Build incrementally, test often
- **AI pair programming**: Use GitHub Copilot or similar tools
- **Focus on core value**: Prioritize working system over perfect code
- **Document trade-offs**: Show understanding of decisions made
- **Practice demo**: Rehearse before recording

---