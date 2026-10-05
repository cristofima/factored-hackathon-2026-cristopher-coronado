/**
 * Built-in widgets initialization
 * Registers pre-built widgets with the widget registry
 */

import { widgetRegistry } from "./WidgetRegistry";
import { ToolApprovalRequest } from "./common/ToolApprovalRequest";
import { DisputeConsent } from "./common/DisputeConsent";
import { DisputePreview } from "./common/DisputePreview";

/**
 * Register all built-in widgets
 * This should be called once during application initialization
 */
export function registerBuiltInWidgets() {
  // Register the tool approval request widget
  // Support both hyphen and underscore naming conventions
  widgetRegistry.register("tool-approval-request", ToolApprovalRequest);
  widgetRegistry.register("tool_approval_request", ToolApprovalRequest);
  widgetRegistry.register("dispute-consent", DisputeConsent);
  widgetRegistry.register("dispute_consent", DisputeConsent);
  widgetRegistry.register("dispute_preview", DisputePreview);
  widgetRegistry.register("dispute-preview", DisputePreview);
}

// Auto-register on module load
registerBuiltInWidgets();
