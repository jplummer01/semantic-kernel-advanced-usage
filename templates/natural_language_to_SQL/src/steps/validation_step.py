import sys
sys.path.append("../../")

from rich.console import Console
from semantic_kernel.processes.kernel_process import KernelProcessStep, KernelProcessStepContext
from semantic_kernel.kernel import Kernel
from semantic_kernel.functions import kernel_function

from src.models.events import SQLEvents
from src.models.step_models import (
    ValidationStepInput,
    ExecutionStepInput,
    SQLGenerationStepInput,
    ValidationResult
)
from src.utils.chat_helpers import call_chat_completion_structured_outputs
from src.constants.data_model import global_database_model
from src.constants.prompts import sql_validation_prompt

console = Console()
issue_history = []

class ValidationStep(KernelProcessStep):

    async def _validate_sql(self, kernel: Kernel, user_query: str, data: ValidationStepInput) -> ValidationResult:
        """Validate the SQL statement against database schema and query standards."""
        relevant_tables = []
        for table in data.table_column_names.table_column_list:
            for model_table in global_database_model:
                if table.table_name == model_table['TableName']:
                    relevant_tables.append(model_table)
                    break

        prompt = sql_validation_prompt.format(
            question=user_query, 
            sql_query=data.sql_statement, 
            table_column_names=relevant_tables
        )
        validation_result = await call_chat_completion_structured_outputs(kernel, prompt, ValidationResult)
        console.print(f"SQL validation results:\n", validation_result)
        return validation_result


    @kernel_function(name="validate_sql")
    async def validate_sql(self, context: KernelProcessStepContext, data: ValidationStepInput, kernel: Kernel):
        """Kernel function to validate SQL and emit the appropriate event."""
        global issue_history
        print("Running ValidationStep...")
        print(f"SQL statement to validate: {data.sql_statement}")

        validation_result = await self._validate_sql(kernel=kernel, user_query=data.user_query, data=data)

        if validation_result.status == "OK":
            # Validation passed, proceed to execution
            result = ExecutionStepInput(
                user_query=data.user_query,
                table_column_names=data.table_column_names,
                sql_statement=data.sql_statement
            )
            await context.emit_event(process_event=SQLEvents.ValidationPassed, data=result)
            print("Emitted event: ValidationPassed.")
        else:
            # Validation failed, return to SQL generation with notes
            notes = f"Validation failed: {str(validation_result)}\nPrevious SQL Statement (need to improve):\n{data.sql_statement}"
            issue_history.append(notes)
            result = SQLGenerationStepInput(
                user_query=data.user_query, 
                table_column_names=data.table_column_names,
                notes="\n\n".join(issue_history)
            )
            await context.emit_event(process_event=SQLEvents.ValidationFailed, data=result)
            print("Emitted event: ValidationFailed.")