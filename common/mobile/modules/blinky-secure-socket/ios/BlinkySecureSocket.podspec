require 'json'

package = JSON.parse(File.read(File.join(__dir__, '..', 'package.json')))

Pod::Spec.new do |s|
  s.name = 'BlinkySecureSocket'
  s.version = package['version']
  s.summary = 'Pinned WSS and secure credential storage for Blinky.'
  s.description = s.summary
  s.license = { :type => 'MIT', :file => '../../../LICENSE' }
  s.author = 'Blinky contributors'
  s.homepage = 'https://github.com/KingSahil/Blinky'
  s.source = { :git => 'https://github.com/KingSahil/Blinky.git' }
  s.platforms = { :ios => '15.1' }
  s.swift_version = '5.9'
  s.static_framework = true
  s.dependency 'ExpoModulesCore'
  s.source_files = '**/*.{h,m,swift}'
  s.pod_target_xcconfig = { 'DEFINES_MODULE' => 'YES' }
end
