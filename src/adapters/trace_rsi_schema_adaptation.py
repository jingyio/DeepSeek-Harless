"""根据真实合格对象放宽 required；不改算法、字段类型或闭合对象约束。"""
import copy


def adapt_required_fields(schema, values):
    if type(values) is not list or not values:
        raise ValueError('witnessed_schema_values_required')
    changes = []

    def visit(original, observed, path):
        result = copy.deepcopy(original)
        if not observed:
            return result
        kind = result.get('type')
        expected = {'object': dict, 'array': list, 'string': str, 'boolean': bool, 'integer': int}
        if kind in expected and any(type(v) is not expected[kind] for v in observed):
            raise ValueError('schema_type_change_not_allowed')
        if kind == 'object':
            if result.get('additionalProperties') is not False:
                raise ValueError('closed_object_schema_required')
            properties = result['properties']
            if any(set(v) - set(properties) for v in observed):
                raise ValueError('unknown_witness_field_not_allowed')
            old = result.get('required', [])
            result['required'] = [k for k in old if all(k in v for v in observed)]
            if old != result['required']:
                changes.append({'path': path, 'old_required': old, 'new_required': result['required'],
                                'observed_objects': len(observed)})
            for key, child in properties.items():
                result['properties'][key] = visit(child, [v[key] for v in observed if key in v],
                    path + '/properties/' + key.replace('~', '~0').replace('/', '~1'))
        elif kind == 'array':
            result['items'] = visit(result['items'], [x for v in observed for x in v], path + '/items')
        return result

    return {'schema': visit(schema, values, ''), 'changes': changes,
            'scope': 'required_only_closed_types_unchanged'}
