# Multi-Step Services Framework

## Overview

The Multi-Step Services Framework is a sophisticated system designed to handle complex, stateful interactions through a series of interconnected steps. It provides a declarative approach to defining service workflows with automatic dependency management, validation, and state persistence.

## Core Concepts

### Service Definition
Each service is defined through a **ServiceDefinition** that acts as the single source of truth for all service behavior. This definition includes:
- Service metadata (name, description)
- Complete step specifications
- Dependency relationships
- Validation rules

### Steps and Substeps
The framework supports **infinite nested substeps**, allowing for complex hierarchical data structures:
- **Main Steps**: Top-level operations (e.g., `user_info`, `account_info`)
- **Substeps**: Nested operations within main steps (e.g., `user_info.address.coordinates.precision.level`)
- **Infinite Nesting**: No limit to substep depth, supporting complex real-world data structures

### Data Types and Examples
Each step is defined with a **payload_example** that serves dual purposes:
- **Documentation**: Shows expected data structure and format
- **Type Detection**: Framework automatically detects how to handle data based on example structure
- **Validation Template**: Provides reference for validating incoming data

## Architecture Components

### 1. Step Information (StepInfo)
Defines individual steps with:
- **Core Properties**: Name, description, required status
- **Dependencies**: Prerequisites that must be completed first
- **Payload Examples**: Expected data structure and format
- **Infinite Substeps**: Recursive substep definitions for complex structures

### 2. Service Definition (ServiceDefinition)
Central orchestrator that:
- **Manages Dependencies**: Calculates available steps based on current state
- **Delegates Responsibilities**: Uses specialized engines for different concerns
- **Generates Schemas**: Creates dynamic JSON schemas for current service state
- **Validates Structures**: Ensures data integrity across all steps

### 3. Specialized Engines

#### Dependency Engine
- **Topological Sorting**: Determines correct step execution order
- **Prerequisite Validation**: Ensures dependencies are satisfied before step execution
- **Completion Detection**: Identifies when services are fully completed
- **State Analysis**: Analyzes current progress and available actions

#### Validation Engine
- **Bulk Processing**: Handles multiple step validations in single operation
- **Substep Mapping**: Maps flat input to nested structures automatically
- **Error Aggregation**: Collects and categorizes validation errors
- **Dependency Cross-Validation**: Ensures dependencies remain valid during updates

#### Visualization Engine
- **Progress Tracking**: Visual representation of completion status
- **Dependency Trees**: ASCII art showing step relationships
- **State Summaries**: Human-readable progress descriptions
- **Next Action Suggestions**: Intelligent recommendations for next steps

### 4. Base Service
Abstract foundation for all services providing:
- **State Management**: Persistent data storage and retrieval
- **Step Execution**: Framework for processing individual steps
- **Validation Hooks**: Integration points for custom validation logic
- **Completion Logic**: Standardized completion detection and messaging

## Data Flow and Processing

### 1. Request Processing
1. **Payload Reception**: Framework receives structured data payload
2. **Service Resolution**: Identifies target service from registry
3. **State Loading**: Retrieves current service state for user
4. **Bulk Validation**: Processes all payload fields simultaneously

### 2. Validation Pipeline
1. **Structure Validation**: Ensures payload matches expected format
2. **Dependency Checking**: Verifies prerequisites are satisfied
3. **Business Validation**: Applies service-specific validation rules
4. **Cross-Field Validation**: Checks relationships between fields

### 3. State Management
1. **Atomic Updates**: All valid changes applied together
2. **Error Isolation**: Invalid fields rejected without affecting valid ones
3. **State Persistence**: Automatic saving after successful processing
4. **User Isolation**: Complete separation of state between different users

### 4. Response Generation
1. **State Analysis**: Comprehensive analysis of current service state
2. **Schema Generation**: Dynamic schema for available next steps
3. **Progress Calculation**: Completion percentages and status
4. **Visualization**: ASCII art trees and progress indicators

## Advanced Features

### Infinite Nested Substeps
The framework supports arbitrarily deep nesting structures:
- **Dot Notation**: Access nested fields using `parent.child.grandchild` syntax
- **Recursive Validation**: Validates structure at all nesting levels
- **Automatic Assembly**: Converts flat inputs to nested JSON structures
- **Type Conversion**: Intelligent type conversion based on examples

### Hybrid Input Modes
Services can accept data in multiple formats:
- **Individual Substeps**: Send one field at a time (`name: "John"`)
- **Partial Groups**: Send subset of related fields
- **Complete Structures**: Send entire nested JSON objects
- **Mixed Approaches**: Combine different input styles within same service

### Dynamic Schema Generation
Schemas adapt to current service state:
- **Context-Aware**: Only shows currently available steps
- **Dependency-Driven**: Updates based on completed prerequisites
- **Example-Rich**: Includes payload examples for all available steps
- **Validation-Ready**: Provides complete validation information

### State Visualization
Rich visual feedback for service progress:
- **ASCII Trees**: Hierarchical view of step dependencies
- **Progress Indicators**: Visual completion status with percentages
- **Status Icons**: Color-coded indicators for different step states
- **Interactive Guidance**: Suggestions for next actions

## Service Lifecycle

### 1. Initialization
- Service instance created with user-specific identifier
- Empty state established with no completed steps
- Available steps calculated based on dependencies
- Initial schema generated for first available actions

### 2. Progressive Completion
- Steps completed incrementally as data provided
- Dependencies automatically unlock new available steps
- State persisted after each successful operation
- Progress tracked and visualized throughout process

### 3. Validation and Error Handling
- Comprehensive validation at each step
- Detailed error messages for invalid data
- Partial success handling (valid steps saved, invalid rejected)
- Recovery guidance for error resolution

### 4. Completion
- Automatic detection when all required steps finished
- Completion message generated with service summary
- Final state preserved for future reference
- Optional steps remain available for additional data

## Benefits and Characteristics

### Developer Experience
- **Declarative Configuration**: Define behavior through data structures, not code
- **Automatic Orchestration**: Framework handles step coordination automatically
- **Rich Tooling**: Comprehensive visualization and debugging capabilities
- **Type Safety**: Strong validation and type checking throughout

### User Experience
- **Progressive Disclosure**: Only show relevant options at each stage
- **Flexible Input**: Accept data in most convenient format
- **Clear Feedback**: Rich progress indication and error messages
- **Forgiving Design**: Partial completion and error recovery

### System Design
- **Separation of Concerns**: Clean separation between different responsibilities
- **Extensibility**: Easy to add new services and capabilities
- **Maintainability**: Clear architecture with well-defined boundaries
- **Testability**: Comprehensive test coverage with isolated components

## Use Cases

### Form Processing
- Multi-step forms with complex validation
- Progressive data collection with dependency-based field availability
- Rich validation feedback and error handling

### Workflow Management
- Business process automation with step dependencies
- State tracking through complex multi-stage operations
- Conditional flow based on previous step results

### Data Integration
- Complex data structure assembly from multiple sources
- Validation and transformation pipelines
- Incremental data building with automatic structure management

### Configuration Management
- Step-by-step system configuration
- Dependency-aware setting management
- Validation of configuration completeness and consistency

This framework provides a robust foundation for building complex, stateful services with rich validation, automatic dependency management, and excellent developer and user experiences.