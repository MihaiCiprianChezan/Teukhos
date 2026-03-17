# Coding Philosophy

- KSCM—Keep It Simple, Smart, Clean, and Maintainable
- Senior-level code—Don't dumb it down
- Simple error handling—Just log with traceback
- Intelligent complexity—Use it when needed, not for its own sake
- Simple, Direct, No unnecessary complexity, Respects the reader's intelligence
- README.md and CHANGELOG.md should be always be updated when the code is changed.

## Core Principles

**Keep It Simple, Smart, Clean, and Maintainable — KSCM**

### 1. **Smart-Simple, Not Over-Engineered**
- **Goal**: Maximum functionality with minimum complexity
- **Approach**: Write intelligently to achieve more with less code
- **Avoid**: Enterprise-level abstractions, unnecessary layers, premature optimization

### 2. **Single Developer + AI Team**
- **Team Size**: One human developer and AI assistants
- **Implication**: No need for enterprise patterns, complex abstractions, or team coordination overhead
- **Focus**: Direct, readable, maintainable code that one person can understand and control

### 3. **Maintainability Over Scalability**
- **Priority**: Code that's straightforward to understand, modify, and debug
- **Avoid**: Complex dependency injection, service meshes, microservices
- **Prefer**: Simple functions, clear data flow, minimal abstractions


## Code Quality Standards

**Readability**
Senior Software Engineer with 10+ year Python programming experience, no need to make the code stupid just to make it understandable to less experienced persons. But the code and the flows should be logical and understandable.
**Python Error Handling**
Unified, standardized, all exception are logged/printed with "The error message: {e}, {traceback.format_exec()}"


# **What We Built vs. What We Needed**
### **The Over-Engineering Trap**
- **Problem**: Building solutions for problems that don't exist
- **Solution**: Start simple, add complexity only when needed
- **Sign**: If you can't explain the code in 30 seconds, it's probably too complex
- **Complexity** We should avoid stupid code and still prioritize intelligent code, ideally minimal, but if and when needed complexity can be used.  
