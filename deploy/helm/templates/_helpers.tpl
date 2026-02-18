{{- define "schemapilot.name" -}}
schemapilot
{{- end -}}

{{- define "schemapilot.labels" -}}
app.kubernetes.io/name: {{ include "schemapilot.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
