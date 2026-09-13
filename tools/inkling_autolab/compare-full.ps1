param([Parameter(Mandatory=$true)][string]$Model,
      [Parameter(Mandatory=$true)][string]$Cases,
      [ValidateSet('baseline','direct','tiles','mapped')][string]$Arm='baseline',
      [int]$Tokens=64, [int]$Samples=3, [string]$Out='',
      [string]$RouteTrace='', [string]$LayerProfile='', [switch]$AllowFixture)
$ErrorActionPreference = 'Stop'
$root = 'C:\Users\devcloud\inkling-autolab'
# Every arm uses the same newly qualified binary/compiler. Baseline arithmetic
# must also match the independently frozen full-decode.exe's full-model hash.
$options = @{
    Model=$Model; Cases=$Cases; Tokens=$Tokens; Samples=$Samples; Out=$Out;
    Binary='full-mmap-embed.exe'; Reads=0; Bf16Rows=1; Int4Rows=1; MmapEmbed=0;
    RouteTrace=$RouteTrace; LayerProfile=$LayerProfile; AllowFixture=$AllowFixture
}
if ($Arm -in @('direct','tiles','mapped')) { $options.Reads = 1 }
if ($Arm -in @('tiles','mapped')) { $options.Bf16Rows = 2; $options.Int4Rows = 4 }
if ($Arm -eq 'mapped') { $options.MmapEmbed = 1 }
"arm=$Arm"
& "$root\run-full.ps1" @options
exit $LASTEXITCODE
