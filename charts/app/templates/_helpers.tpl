{{- define "app.name" -}}
{{- /* Prefer the configured global name; fall back to the chart name. */ -}}
{{- default .Chart.Name .Values.spec.global.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.fullname" -}}
{{- if .Values.spec.global.name -}}
{{- .Values.spec.global.name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- include "app.name" . -}}
{{- end -}}
{{- end -}}

{{- define "app.workloadName" -}}
{{- $root := index . 0 -}}
{{- $workload := index . 1 -}}
{{- $appName := include "app.fullname" $root -}}
{{- $workloadName := $workload.name -}}
{{- if and $workloadName (hasPrefix (printf "%s-" $appName) $workloadName) -}}
{{- $workloadName | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" $appName $workloadName | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "app.commonLabels" -}}
app.kubernetes.io/name: {{ include "app.name" . | quote }}
app.kubernetes.io/instance: {{ .Release.Name | quote }}
app.kubernetes.io/part-of: {{ include "app.name" . | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service | quote }}
{{- end -}}

{{- define "app.selectorLabels" -}}
{{- $root := index . 0 -}}
{{- $workload := index . 1 -}}
app.kubernetes.io/name: {{ include "app.name" $root | quote }}
app.kubernetes.io/instance: {{ $root.Release.Name | quote }}
app.kubernetes.io/component: {{ $workload.name | quote }}
{{- end -}}

{{- define "app.serviceAccountName" -}}
{{- $root := index . 0 -}}
{{- $workload := index . 1 -}}
{{- $global := default (dict) $root.Values.spec.global -}}
{{- $serviceAccount := default (dict) $global.serviceAccount -}}
{{- if $workload.serviceAccountName -}}
{{- $workload.serviceAccountName -}}
{{- else if $serviceAccount.name -}}
{{- $serviceAccount.name -}}
{{- else if $serviceAccount.create -}}
{{- include "app.fullname" $root -}}
{{- else -}}
{{- "" -}}
{{- end -}}
{{- end -}}

{{- define "app.imagePullSecrets" -}}
{{- $global := default (dict) .Values.spec.global -}}
{{- $secrets := default (list "ghcr-pull") $global.imagePullSecrets -}}
{{- if gt (len $secrets) 0 }}
imagePullSecrets:
{{- range $secret := $secrets }}
- name: {{ $secret | quote }}
{{- end }}
{{- end }}
{{- end -}}

{{- define "app.csiVolumeName" -}}
{{- $workload := index . 1 -}}
{{- printf "%s-csi" $workload.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.dotenvVolumeName" -}}
{{- $workload := index . 1 -}}
{{- printf "%s-dotenv" $workload.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.runtimeConfigVolumeName" -}}
{{- $workload := index . 1 -}}
{{- printf "%s-runtime-config" $workload.name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.runtimeConfigMapName" -}}
{{- $workload := index . 1 -}}
{{- printf "%s-runtime-config" (include "app.workloadName" (list (index . 0) $workload)) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "app.tlsSecretName" -}}
{{- $root := index . 0 -}}
{{- $workload := index . 1 -}}
{{- $global := default (dict) $root.Values.spec.global -}}
{{- $tls := default (dict) $global.tls -}}
{{- if and $workload.ingress $workload.ingress.tls $workload.ingress.tls.secretName -}}
{{- $workload.ingress.tls.secretName -}}
{{- else if $tls.secretName -}}
{{- $tls.secretName -}}
{{- else -}}
{{- printf "%s-tls" (include "app.workloadName" (list $root $workload)) -}}
{{- end -}}
{{- end -}}

{{- define "app.resolveResources" -}}
{{- $root := index . 0 -}}
{{- $workload := index . 1 -}}
{{- $resolved := dict -}}
{{- if $workload.resources -}}
  {{- if $workload.resources.requests -}}
    {{- $_ := set $resolved "requests" $workload.resources.requests -}}
  {{- end -}}
  {{- if $workload.resources.limits -}}
    {{- $_ := set $resolved "limits" $workload.resources.limits -}}
  {{- end -}}
  {{- if and (eq (len $resolved) 0) $workload.resources.preset $root.Values.spec.global.resourcePresets -}}
    {{- $preset := index $root.Values.spec.global.resourcePresets $workload.resources.preset -}}
    {{- if $preset -}}
      {{- if $preset.requests -}}
        {{- $_ := set $resolved "requests" $preset.requests -}}
      {{- end -}}
      {{- if $preset.limits -}}
        {{- $_ := set $resolved "limits" $preset.limits -}}
      {{- end -}}
    {{- end -}}
  {{- end -}}
{{- end -}}
{{- if gt (len $resolved) 0 -}}
{{- toYaml $resolved -}}
{{- end -}}
{{- end -}}

{{- define "app.renderCommand" -}}
{{- $workload := index . 0 -}}
{{- $command := $workload.command -}}
{{- if kindIs "string" $command -}}
  {{- if ne (trim $command) "" -}}
command:
  - sh
  - -lc
  - {{ $command | quote }}
  {{- end -}}
{{- else if kindIs "slice" $command -}}
  {{- if gt (len $command) 0 -}}
command:
{{ toYaml $command | nindent 2 }}
  {{- end -}}
{{- end -}}
{{- end -}}

