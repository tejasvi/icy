Icy lets you skip closing braces and semicolons by applying indentation based deduction rules.

Letting you write:

```c++
void BFCAllocator::SetSafeFrontier(uint64 count) {
  uint64 current = safe_frontier_.load(std::memory_order_relaxed)
  while (count > current) {
    if (safe_frontier_.compare_exchange_strong(current, count)) {
      retry_helper_.NotifyDealloc()
      return
    else {
      current = safe_frontier_.load(std::memory_order_relaxed)
```

instead of:

```c++
void BFCAllocator::SetSafeFrontier(uint64 count) {
  uint64 current = safe_frontier_.load(std::memory_order_relaxed);
  while (count > current) {
    if (safe_frontier_.compare_exchange_strong(current, count)) {
      retry_helper_.NotifyDealloc();
      return;
    } else {
      current = safe_frontier_.load(std::memory_order_relaxed);
    }
  }
}
```

# Brace the rules
1. Strings, comments, trailing whitespace and empty lines are ignored.
1. If next line has higher indentation, both lines are treated as same logical line.
    * ```c++
      ScopeExitGuard(const bool callOnScopeExit_,
                     F &&onScopeExit_,
                     m_callOnScopeExit(callOnScopeExit_),
                     m_onScopeExit(std::forward<F>(onScopeExit_))
      ```
1. If a line ends with an opening brace and next line has exactly *one* level higher indentation, it marks the start of a block.
    * ```c++
      namespace guard { // Not a block. Must close manually
      if (m_callOnScopeExit) { // Block
          m_onScopeExit()
      std::cout << "Enter"; // Block closed
      ```
1. The line after the next logical line with indentation equal or lower than the block's start marks the end of the block.
    * ```c++
      ScopeExitGuard(ScopeExitGuard<G> &&other)
          : m_callOnScopeExit(true) { // Block start at logical line's indent 0
        other.m_callOnScopeExit = false;

      ~ScopeExitGuard() { // Previous block ends
        if (m_callOnScopeExit) {
          m_onScopeExit();
      ```
1. If a logical line has indentation equal or greater than the next line, it is treated as a statement and appended with a semi-colon.
    * The line must not end with `{ ; , : < ( [ =`.
    * Exception for isolated template declarations.
        * ```c++
          template <typename G> // Not a statement
          ScopeExitGuard(ScopeExitGuard<G> &&other)
              : m_callOnScopeExit(true) {
            other.m_callOnScopeExit = false // Statement
            std::cout << "Exit" // Statement
          void f();
          ```

# Extras
* Icy can seamlessly integrated with existing C++ tooling since the brace and semi-colon addition is done only on the line ends. TODO: Extensions for popular editors. Should be trivial.
* Decompilation involves clang-format with following configuration.
  ```
  LambdaBodyIndentation: Signature
  IndentGotoLabels: true
  IndentExternBlock: Indent
  BreakBeforeBraces: Attach
  AllowAllArgumentsOnNextLine: false
  Cpp11BracedListStyle: false
  IndentRequires: true
  IndentWrappedFunctionNames: true
  NamespaceIndentation: All
  UseTab: Never
  CompactNamespaces: false
  ```
  Closing braces and semi-colons are removed if Icy compiler can deduce them from the indentation of formatted code.

# Related works
There have been a few attempts at trimming the C++ syntax but have ended up being too disruptive.
* [coffeepp](https://github.com/jhasse/coffeepp)
* [CPY](https://github.com/vrsperanza/CPY)
* [SugerCPP](https://github.com/curimit/SugarCpp)
