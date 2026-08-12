<?php
/**
 * Mistral.ai Conversations API Client
 * 
 * This script sends a request to the Mistral.ai Conversations API with
 * partially base64-encoded text in the request body.
 */

// Configuration
$apiKey = 'YOUR_MISTRAL_API_KEY'; // Replace with your actual Mistral API key
$apiUrl = 'https://api.mistral.ai/v1/conversations';

// Sample text - part of it will be base64 encoded
$originalText = "This is a sample text for Mistral AI API. The quick brown fox jumps over the lazy dog.";

// Partially encode the text: encode the second half
$textParts = explode(' ', $originalText, 2);
$firstPart = $textParts[0] ?? '';
$secondPart = $textParts[1] ?? '';

// Base64 encode the second part
$encodedPart = base64_encode($secondPart);

// Construct the partially encoded body
$requestBody = [
    'model' => 'mistral-tiny', // or 'mistral-small', 'mistral-medium', etc.
    'messages' => [
        [
            'role' => 'user',
            'content' => $firstPart . ' [BASE64:' . $encodedPart . ']',
            // Alternatively, you could structure it differently:
            // 'content' => $firstPart,
            // 'encoded_content' => $encodedPart,
            // 'encoding' => 'base64'
        ]
    ],
    'temperature' => 0.7,
    'max_tokens' => 100,
    'top_p' => 1.0,
];

// Alternative approach: Send both raw and encoded versions
$alternativeRequestBody = [
    'model' => 'mistral-tiny',
    'messages' => [
        [
            'role' => 'user',
            'content' => $originalText,
            'metadata' => [
                'encoded_part' => $encodedPart,
                'encoding_scheme' => 'partial_base64',
                'original_length' => strlen($originalText),
                'encoded_length' => strlen($encodedPart)
            ]
        ]
    ],
    'temperature' => 0.7,
    'max_tokens' => 100,
];

// Headers for the API request
$headers = [
    'Content-Type: application/json',
    'Accept: application/json',
    'Authorization: Bearer ' . $apiKey,
];

// Initialize cURL
$ch = curl_init();

// Set cURL options
curl_setopt($ch, CURLOPT_URL, $apiUrl);
curl_setopt($ch, CURLOPT_POST, true);
curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
curl_setopt($ch, CURLOPT_RETURNTRANSFER, true);
curl_setopt($ch, CURLOPT_SSL_VERIFYPEER, true);
curl_setopt($ch, CURLOPT_SSL_VERIFYHOST, 2);

// Use the alternative request body (with metadata)
$jsonBody = json_encode($alternativeRequestBody, JSON_PRETTY_PRINT);
curl_setopt($ch, CURLOPT_POSTFIELDS, $jsonBody);

// Execute the request
$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$error = curl_error($ch);

// Close cURL
curl_close($ch);

// Process the response
echo "=== Mistral.ai Conversations API Request ===\n\n";
echo "Request URL: $apiUrl\n";
echo "HTTP Method: POST\n";
echo "HTTP Code: $httpCode\n\n";

echo "Request Body:\n";
echo "----------------------------------------\n";
echo $jsonBody . "\n\n";

echo "Response:\n";
echo "----------------------------------------\n";

if ($error) {
    echo "cURL Error: $error\n";
} else {
    // Pretty print JSON response
    $decodedResponse = json_decode($response, true);
    if (json_last_error() === JSON_ERROR_NONE) {
        echo json_encode($decodedResponse, JSON_PRETTY_PRINT) . "\n";
    } else {
        echo "Raw Response:\n";
        echo $response . "\n";
    }
}

echo "\n=== Decoding Example ===\n";
echo "Original second part: $secondPart\n";
echo "Base64 encoded: $encodedPart\n";
echo "Decoded back: " . base64_decode($encodedPart) . "\n";

// Function to create a request with custom encoding
function createPartiallyEncodedRequest($text, $encodeFromPosition = 0) {
    $chars = str_split($text);
    $encodedParts = [];
    
    for ($i = 0; $i < count($chars); $i++) {
        if ($i >= $encodeFromPosition) {
            // Encode from this position onward
            $remaining = implode('', array_slice($chars, $i));
            $encodedParts[] = base64_encode($remaining);
            break;
        } else {
            $encodedParts[] = $chars[$i];
        }
    }
    
    return [
        'original' => $text,
        'partially_encoded' => implode('', $encodedParts),
        'encode_position' => $encodeFromPosition
    ];
}

// Example usage of the function
$customEncoded = createPartiallyEncodedRequest($originalText, 5);
echo "\nCustom Encoding Example:\n";
echo "Original: {$customEncoded['original']}\n";
echo "Partially Encoded: {$customEncoded['partially_encoded']}\n";
echo "Decoded: " . base64_decode(explode('[BASE64:', $customEncoded['partially_encoded'])[1] ?? '') . "\n";

?>