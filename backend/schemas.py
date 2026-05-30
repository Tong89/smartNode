# -*- coding: utf-8 -*-
"""请求体严格校验（轻量、零依赖）。

对提交/配置接口做类型、范围、枚举与字段白名单校验，拒绝未知字段与越界输入，返回字段级错误。
"""


class ValidationError(Exception):
    def __init__(self, errors):
        super().__init__("validation failed")
        self.errors = errors


def _err(field, message):
    return {"field": field, "message": message}


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


SUBMIT_ALLOWED_FIELDS = {
    "data_type", "data_size", "priority", "max_delay", "satellite_id",
    "selected_ground_stations", "start_time", "end_time",
    "start_time_offset", "time_window_duration", "experiment_requirements",
    "custom_constraints",
}


def validate_request_submission(data, allowed_data_types=None):
    if not isinstance(data, dict):
        raise ValidationError([_err("body", "必须为 JSON 对象")])

    errors = []
    for unknown in set(data.keys()) - SUBMIT_ALLOWED_FIELDS:
        errors.append(_err(unknown, "未知字段，已拒绝"))

    dt = data.get("data_type")
    if not isinstance(dt, str) or not dt:
        errors.append(_err("data_type", "必填，且须为非空字符串"))
    elif allowed_data_types is not None and dt not in allowed_data_types:
        errors.append(_err("data_type", f"不支持的数据类型: {dt}"))

    ds = data.get("data_size")
    if not _is_number(ds) or ds <= 0:
        errors.append(_err("data_size", "必填，且须为正数"))

    pr = data.get("priority")
    if pr is not None and (not _is_int(pr) or not (0 <= pr <= 10)):
        errors.append(_err("priority", "须为 0-10 的整数"))

    md = data.get("max_delay")
    if md is not None and (not _is_number(md) or md < 0):
        errors.append(_err("max_delay", "须为非负数"))

    sid = data.get("satellite_id")
    if sid is not None and not isinstance(sid, str):
        errors.append(_err("satellite_id", "须为字符串"))

    gss = data.get("selected_ground_stations")
    if gss is not None and not isinstance(gss, list):
        errors.append(_err("selected_ground_stations", "须为数组"))

    if errors:
        raise ValidationError(errors)
    return data


def validate_count_update(data, lo=None, hi=None):
    if not isinstance(data, dict):
        raise ValidationError([_err("body", "必须为 JSON 对象")])

    errors = []
    for unknown in set(data.keys()) - {"count"}:
        errors.append(_err(unknown, "未知字段，已拒绝"))

    c = data.get("count")
    if not _is_int(c):
        errors.append(_err("count", "必填，且须为整数"))
    else:
        if lo is not None and c < lo:
            errors.append(_err("count", f"不得小于 {lo}"))
        if hi is not None and c > hi:
            errors.append(_err("count", f"不得大于 {hi}"))

    if errors:
        raise ValidationError(errors)
    return data
