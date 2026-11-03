/** M10 表单校验（纯函数，node:test 覆盖）。 */

export type FieldError = { field: string; message: string };

const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d-([01]\d|2[0-3]):[0-5]\d$/;

export function validateLoginForm(username: string, password: string): FieldError[] {
  const errs: FieldError[] = [];
  if (!username.trim()) errs.push({ field: "username", message: "请输入用户名" });
  if (!password) errs.push({ field: "password", message: "请输入口令" });
  return errs;
}

export function validatePoiForm(form: {
  name: string;
  position_x: number;
  position_y: number;
  business_hours: Record<string, string[]>;
}): FieldError[] {
  const errs: FieldError[] = [];
  if (!form.name.trim()) errs.push({ field: "name", message: "名称必填" });
  if (form.name.length > 128) errs.push({ field: "name", message: "名称≤128 字" });
  if (!Number.isFinite(form.position_x)) errs.push({ field: "position_x", message: "X 坐标必填数字" });
  if (!Number.isFinite(form.position_y)) errs.push({ field: "position_y", message: "Y 坐标必填数字" });
  for (const [day, spans] of Object.entries(form.business_hours ?? {})) {
    for (const span of spans) {
      if (!TIME_RE.test(span)) {
        errs.push({ field: "business_hours", message: `${day} 时段格式应为 HH:MM-HH:MM` });
      }
    }
  }
  return errs;
}
