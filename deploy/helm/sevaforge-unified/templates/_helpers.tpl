{{/*
Common name helpers
*/}}
{{- define "sevaforge-unified.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end }}
