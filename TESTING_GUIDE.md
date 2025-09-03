# Interactive Testing Guide

## 🎯 How to Test the Different Approaches

### Quick Start
```bash
# Test the enhanced orchestrated agent (recommended)
uv run src/interactive_test.py orchestrated

# Test the identification service agent
uv run src/interactive_test.py identification

# Test without specifying (will prompt for choice)
uv run src/interactive_test.py
```

## 🧪 Test Scenarios

### 1. User Identification Comparison

**Test with Orchestrated Agent:**
```bash
uv run src/interactive_test.py orchestrated
```
Then try:
- "I need to identify myself"
- "I want to access municipal services"

**Test with Identification Agent:**
```bash
uv run src/interactive_test.py identification
```
Then try:
- "I need to identify myself to access municipal services"
- Provide CPF: "123.456.789-01"
- Provide email: "joao.silva@gmail.com"
- Watch how it handles the conversational flow

### 2. Municipal Services Routing

**Test with Orchestrated Agent:**
```bash
uv run src/interactive_test.py orchestrated
```
Then try:
- "I want to pay my IPTU taxes"
- "I need to report a broken street light"
- "I want to request a birth certificate"
- "I need tax advice for my business"

### 3. Compare Approaches Side by Side

1. **Start with Orchestrated Agent:**
   ```bash
   uv run src/interactive_test.py orchestrated
   ```
   - Try: "I need to identify myself"
   - Note the structured workflow approach

2. **Switch to Identification Agent:**
   - Type: `switch`
   - Choose option 4 (identification)
   - Try: "I need to identify myself"
   - Note the conversational agent approach

## 🔍 What to Look For

### Workflow Approach (via Orchestrated Agent)
- ✅ **Structured flow**: Clear step-by-step process
- ✅ **Fast responses**: Minimal LLM calls
- ✅ **Predictable**: Same flow every time
- ✅ **Validation**: Built-in parameter validation
- ❌ **Less flexible**: Fixed conversation flow

### Service Agent Approach (Identification Agent)
- ✅ **Natural conversation**: Adaptive dialogue
- ✅ **Flexible**: Handles unexpected responses
- ✅ **Reasoning**: Can explain and interpret
- ❌ **Slower**: Multiple LLM calls
- ❌ **Variable**: Different flow each time
- ❌ **More expensive**: Higher token usage

## 🎯 Key Test Cases

### Valid Data Test
- **CPF**: `123.456.789-01` (valid)
- **Email**: `joao.silva@gmail.com`
- **Name**: `João Silva Santos`

### Invalid Data Test
- **CPF**: `111.111.111-11` (invalid - repeated digits)
- **Email**: `invalid-email` (invalid format)
- **Name**: `João` (invalid - no surname)

### Edge Cases
- **CPF**: `12345678901` (unformatted but valid)
- **Email**: `USER@GMAIL.COM` (uppercase)
- **Exit**: Type "exit" at any point in workflow

## 🔧 Interactive Commands

During any chat session:
- `help` - Show available commands
- `switch` - Change to different agent type
- `clear` - Clear the screen
- `quit` - Exit the session

## 📊 Performance Comparison

### What You Should Notice:

**Orchestrated Agent (Workflow):**
- Immediate structured response
- Clear parameter collection steps
- Fast validation feedback
- Consistent user experience

**Identification Agent (Service Agent):**
- Natural language responses
- More conversational flow
- Longer response times
- More token usage (visible in output)

## 🏆 Conclusion Points

After testing both approaches, you should see:

1. **Workflows** are better for:
   - Transactional services (80% of municipal services)
   - High-volume, repetitive processes
   - Cost-sensitive applications

2. **Service Agents** are better for:
   - Consultative services (15% of municipal services)
   - Complex scenarios requiring reasoning
   - Open-ended support conversations

3. **Hybrid Approach** gives you:
   - Best of both worlds
   - Cost optimization
   - Scalability to 50+ services

## 🚀 Next Steps After Testing

Once you've tested both approaches:
1. Note the performance differences
2. Consider which feels better for different use cases
3. Ready to implement more workflows for other municipal services
4. Can proceed with confidence in the hybrid architecture
