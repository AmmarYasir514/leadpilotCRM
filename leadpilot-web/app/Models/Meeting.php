<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Meeting extends Model
{
    protected $fillable = [
        'organization_id',
        'user_id',
        'provider',
        'title',
        'starts_at',
        'ends_at',
        'attendees',
        'meeting_url',
        'external_id',
    ];

    protected function casts(): array
    {
        return [
            'starts_at' => 'datetime',
            'ends_at' => 'datetime',
            'attendees' => 'array',
        ];
    }
}